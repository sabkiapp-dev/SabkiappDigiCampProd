#!/usr/bin/env python3
"""
Real-Time AI Call — ARI + ExternalMedia + Gemini Live API

Call flow:
  Phone ← GSM ← Dinstar ← PJSIP(ulaw) ← Asterisk Bridge
                                              ↕
                                        ExternalMedia (ulaw RTP)
                                              ↕
                                        Python (this script)
                                              ↕
                                        Gemini Live API (WebSocket)

Audio conversion:
  Caller → ulaw(8kHz) → PCM16(8kHz) → resample(16kHz) → Gemini
  Gemini → PCM16(24kHz) → resample(8kHz) → ulaw(8kHz) → Caller

Usage:
  python3 test_04_gemini_live.py --endpoint "PJSIP/9971389164@1017"
  python3 test_04_gemini_live.py --endpoint "PJSIP/NUM@1017" --language hi
"""

import argparse
import asyncio
import audioop
import json
import socket
import struct
import sys
import threading
import time

import requests
import websocket


# ── Gemini Live Session (async) ─────────────────────────────────────────────

class GeminiLiveSession:
    """Bidirectional audio streaming with Gemini Live API."""

    def __init__(self, api_key, model, system_prompt, voice="Puck"):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.voice = voice
        self._session = None
        self._client = None
        self._running = False
        self._audio_out_queue = asyncio.Queue()
        self._receive_task = None
        self._loop = None

    def _build_config(self):
        from google.genai import types
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice,
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=self.system_prompt)]
            ),
        )

    def create_client(self):
        from google import genai
        self._client = genai.Client(api_key=self.api_key)
        self._running = True
        return self._client

    async def send_audio(self, pcm_16k: bytes):
        """Send 16kHz 16-bit PCM to Gemini."""
        if not self._session or not self._running:
            return
        from google.genai import types
        try:
            await self._session.send(
                input=types.LiveClientRealtimeInput(
                    media_chunks=[
                        types.Blob(
                            data=pcm_16k,
                            mime_type="audio/pcm;rate=16000",
                        )
                    ]
                )
            )
        except Exception as e:
            print(f"[GEMINI] Send error: {e}")

    async def get_audio(self) -> bytes:
        """Get next audio chunk from Gemini (24kHz PCM). Blocks until available."""
        return await self._audio_out_queue.get()

    async def _receive_loop(self):
        """Background: read Gemini responses, queue audio chunks."""
        try:
            async for response in self._session.receive():
                if not self._running:
                    break
                server_content = getattr(response, "server_content", None)
                if server_content and server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            await self._audio_out_queue.put(part.inline_data.data)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[GEMINI] Receive error: {e}")


# ── RTP Handler ─────────────────────────────────────────────────────────────

class RTPHandler:
    """UDP socket for ExternalMedia RTP (ulaw format)."""

    def __init__(self, host="127.0.0.1", port=20000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(0.5)
        self.remote_addr = None
        self.packets_in = 0
        self.packets_out = 0
        self.running = False
        # Outbound RTP state
        self._seq = 0
        self._timestamp = 0
        self._ssrc = 0xABCD1234

    def start(self):
        self.sock.bind((self.host, self.port))
        self.running = True
        print(f"[RTP] Listening on {self.host}:{self.port}")

    def stop(self):
        self.running = False
        self.sock.close()

    def receive(self):
        """Receive one RTP packet. Returns (payload_type, ulaw_payload) or None."""
        try:
            data, addr = self.sock.recvfrom(4096)
            self.remote_addr = addr
            self.packets_in += 1
            if len(data) < 12:
                return None
            pt = data[1] & 0x7F
            payload = data[12:]
            return pt, payload
        except socket.timeout:
            return None
        except OSError:
            return None

    def send(self, ulaw_payload: bytes, pt=0):
        """Send ulaw audio back as RTP packet."""
        if not self.remote_addr:
            return
        self._seq = (self._seq + 1) & 0xFFFF
        self._timestamp = (self._timestamp + len(ulaw_payload)) & 0xFFFFFFFF

        header = struct.pack("!BBHII",
            0x80, pt, self._seq, self._timestamp, self._ssrc)
        self.sock.sendto(header + ulaw_payload, self.remote_addr)
        self.packets_out += 1


# ── ARI Call Handler ────────────────────────────────────────────────────────

class ARICallHandler:
    """Manages ARI call lifecycle: originate → bridge → ExternalMedia."""

    def __init__(self, host, port, user, password, app):
        self.base = f"http://{host}:{port}/ari"
        self.ws_url = f"ws://{host}:{port}/ari/events?api_key={user}:{password}&app={app}"
        self.auth = (user, password)
        self.app = app
        self.channel_id = None
        self.bridge_id = None
        self.ext_media_id = None
        self._ws = None
        self.call_start = None
        self.on_call_ready = None   # callback when bridge + ExternalMedia ready
        self.on_call_end = None     # callback when call ends

    def _api(self, method, path, **kwargs):
        resp = requests.request(method, f"{self.base}{path}", auth=self.auth, timeout=10, **kwargs)
        if resp.status_code not in (200, 201, 204):
            print(f"[ARI] {method} {path} → {resp.status_code}: {resp.text[:200]}")
        return resp

    def originate(self, endpoint):
        resp = self._api("POST", "/channels", json={
            "endpoint": endpoint, "app": self.app, "callerId": "AI-Call"})
        if resp.status_code in (200, 201):
            print(f"[ARI] Originate OK — ringing...")
            return True
        print("[ARI] Originate FAILED")
        return False

    def _setup_bridge(self, rtp_host, rtp_port):
        # Create bridge
        resp = self._api("POST", "/bridges", json={"type": "mixing"})
        if resp.status_code not in (200, 201):
            return False
        self.bridge_id = resp.json()["id"]

        # Add caller to bridge
        self._api("POST", f"/bridges/{self.bridge_id}/addChannel",
                  json={"channel": self.channel_id})

        # Create ExternalMedia
        resp = self._api("POST", "/channels/externalMedia", json={
            "app": self.app,
            "external_host": f"{rtp_host}:{rtp_port}",
            "format": "ulaw",
            "encapsulation": "rtp",
            "transport": "udp",
            "direction": "both",
        })
        if resp.status_code in (200, 201):
            self.ext_media_id = resp.json()["id"]
            self._api("POST", f"/bridges/{self.bridge_id}/addChannel",
                      json={"channel": self.ext_media_id})
            print("[ARI] Bridge + ExternalMedia ready")
            return True
        return False

    def cleanup(self):
        if self.bridge_id:
            self._api("DELETE", f"/bridges/{self.bridge_id}")
        if self.ext_media_id:
            self._api("DELETE", f"/channels/{self.ext_media_id}")

    def hangup(self):
        if self.channel_id:
            self._api("DELETE", f"/channels/{self.channel_id}")

    def run_ws(self, rtp_host, rtp_port):
        def on_open(ws):
            print("[ARI] WebSocket connected")

        def on_message(ws, message):
            try:
                event = json.loads(message)
                etype = event.get("type", "")

                if etype == "StasisStart":
                    ch = event["channel"]
                    state = ch.get("state", "?")
                    name = ch.get("name", "?")
                    # Only handle the PJSIP caller channel, not ExternalMedia
                    if self.channel_id is None and "UnicastRTP" not in name:
                        self.channel_id = ch["id"]
                        self.call_start = time.time()
                        print(f"[ARI] Call answered: {name} state={state}")
                        threading.Thread(target=self._do_setup,
                                         args=(rtp_host, rtp_port), daemon=True).start()

                elif etype == "StasisEnd":
                    ch_id = event["channel"]["id"]
                    if ch_id == self.channel_id:
                        dur = time.time() - self.call_start if self.call_start else 0
                        print(f"[ARI] Call ended — duration={dur:.1f}s")
                        self.cleanup()
                        if self.on_call_end:
                            self.on_call_end()
                        ws.close()

                elif etype == "ChannelDtmfReceived":
                    digit = event.get("digit", "?")
                    print(f"[ARI] DTMF: {digit}")
                    if digit == "#":
                        self.hangup()

            except Exception as e:
                print(f"[ARI] Event error: {e}")
                import traceback
                traceback.print_exc()

        def on_error(ws, error):
            print(f"[ARI] WS error: {error}")

        def on_close(ws, code, reason):
            print(f"[ARI] WS closed")

        self._ws = websocket.WebSocketApp(
            self.ws_url, on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        self._ws.run_forever()

    def _do_setup(self, rtp_host, rtp_port):
        if self._setup_bridge(rtp_host, rtp_port):
            if self.on_call_ready:
                self.on_call_ready()


# ── Main: Wire everything together ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Gemini Live AI Call")
    parser.add_argument("--endpoint", required=True, help="e.g. PJSIP/9971389164@1017")
    parser.add_argument("--api-key", default="AIzaSyDxQ4yME9ChXywqmm-6qry_W5RcjhANmnM")
    parser.add_argument("--model", default="gemini-2.5-flash-native-audio-latest")
    parser.add_argument("--voice", default="Kore", help="Gemini voice: Puck, Charon, Kore, Fenrir, Aoede")
    parser.add_argument("--language", default="en", help="Prompt language hint")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8088, type=int)
    parser.add_argument("--user", default="ari_user")
    parser.add_argument("--password", default="ari_pass")
    parser.add_argument("--rtp-host", default="127.0.0.1")
    parser.add_argument("--rtp-port", default=20000, type=int)
    args = parser.parse_args()

    lang_prompts = {
        "en": "You are a friendly voice assistant on a phone call. Keep responses short and conversational. Speak in English.",
        "hi": "You are a friendly voice assistant on a phone call. Keep responses short and conversational. Speak in Hindi (Hinglish is okay).",
    }
    system_prompt = lang_prompts.get(args.language, lang_prompts["en"])

    print("=" * 55)
    print("  GEMINI LIVE AI CALL")
    print("=" * 55)
    print(f"  Endpoint : {args.endpoint}")
    print(f"  Model    : {args.model}")
    print(f"  Voice    : {args.voice}")
    print(f"  Language : {args.language}")
    print("=" * 55)
    print()

    # ── Components ──
    rtp = RTPHandler(args.rtp_host, args.rtp_port)
    ari = ARICallHandler(args.host, args.port, args.user, args.password, "ai-call-app")
    gemini = GeminiLiveSession(args.api_key, args.model, system_prompt, args.voice)

    # Shared state
    call_active = threading.Event()
    call_ended = threading.Event()

    def on_call_ready():
        print("[MAIN] Call ready — starting AI pipeline")
        call_active.set()

    def on_call_end():
        print("[MAIN] Call ended — stopping AI pipeline")
        call_active.clear()
        call_ended.set()

    ari.on_call_ready = on_call_ready
    ari.on_call_end = on_call_end

    # ── Async audio pipeline ──

    async def audio_pipeline():
        """Main audio loop: RTP ↔ Gemini Live."""
        from google.genai import types

        client = gemini.create_client()
        config = gemini._build_config()

        print(f"[GEMINI] Connecting (model={gemini.model}, voice={gemini.voice})...")

        async with client.aio.live.connect(model=gemini.model, config=config) as session:
            print("[GEMINI] Connected!")
            print("[PIPELINE] Running — speak into the phone!")

            audio_out_queue = asyncio.Queue()

            # Task 0: Receive Gemini responses → queue audio
            async def receive_gemini():
                try:
                    async for response in session.receive():
                        if not call_active.is_set():
                            break
                        sc = getattr(response, "server_content", None)
                        if sc and sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    await audio_out_queue.put(part.inline_data.data)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    print(f"[GEMINI] Receive error: {e}")

            # Task 1: RTP → Gemini (caller's voice → AI)
            async def feed_gemini():
                while call_active.is_set():
                    result = await asyncio.get_event_loop().run_in_executor(None, rtp.receive)
                    if result is None:
                        continue
                    pt, ulaw_data = result
                    # ulaw(8kHz) → PCM16(8kHz) → resample(16kHz)
                    pcm_8k = audioop.ulaw2lin(ulaw_data, 2)
                    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
                    await session.send(
                        input=types.LiveClientRealtimeInput(
                            media_chunks=[types.Blob(
                                data=pcm_16k,
                                mime_type="audio/pcm;rate=16000",
                            )]
                        )
                    )

            # Task 2: Gemini → RTP (AI response → caller)
            async def play_gemini():
                while call_active.is_set():
                    try:
                        pcm_24k = await asyncio.wait_for(audio_out_queue.get(), timeout=0.5)
                        # PCM16(24kHz) → resample(8kHz) → ulaw
                        pcm_8k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, 8000, None)
                        ulaw_data = audioop.lin2ulaw(pcm_8k, 2)
                        # Send in 160-byte chunks (20ms frames for ulaw 8kHz)
                        for i in range(0, len(ulaw_data), 160):
                            chunk = ulaw_data[i:i+160]
                            if len(chunk) == 160:
                                rtp.send(chunk, pt=0)
                    except asyncio.TimeoutError:
                        continue

            await asyncio.gather(receive_gemini(), feed_gemini(), play_gemini())

    def run_pipeline():
        """Run async pipeline in its own event loop."""
        # Wait for call to be ready
        call_active.wait()
        # Small delay for RTP to start flowing
        time.sleep(0.5)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(audio_pipeline())
        except Exception as e:
            print(f"[PIPELINE] Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            loop.close()

    # ── Start everything ──

    rtp.start()

    # Pipeline thread (waits for call_active)
    pipeline_thread = threading.Thread(target=run_pipeline, daemon=True)
    pipeline_thread.start()

    # Originate call
    threading.Thread(target=lambda: (
        time.sleep(1),
        ari.originate(args.endpoint)
    ), daemon=True).start()

    # ARI WebSocket (blocks until call ends)
    try:
        ari.run_ws(args.rtp_host, args.rtp_port)
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted")
        call_active.clear()
        ari.hangup()
        ari.cleanup()

    # Wait for pipeline to finish
    call_ended.wait(timeout=5)
    rtp.stop()

    print()
    print("=" * 55)
    print(f"  RTP in: {rtp.packets_in}  out: {rtp.packets_out}")
    dur = time.time() - ari.call_start if ari.call_start else 0
    print(f"  Duration: {dur:.1f}s")
    print("=" * 55)


if __name__ == "__main__":
    main()
