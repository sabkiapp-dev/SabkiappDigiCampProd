#!/usr/bin/env python3
"""
RPi Audio Bridge — Runs on RPi. Bridges ARI ExternalMedia RTP ↔ Dev PC WebSocket.

Does NO AI processing — just forwards audio:
  ExternalMedia (ulaw RTP) → WebSocket → Dev PC (ai_server.py)
  Dev PC (ai_server.py) → WebSocket → ExternalMedia (ulaw RTP)

Usage:
    python3 rpi_audio_bridge.py --endpoint "PJSIP/8757839258@1017" --server "ws://192.168.8.7:9090"
"""

import argparse
import json
import queue
import socket
import struct
import sys
import threading
import time

import requests
import websocket as ws_client

import silero_vad


class RTPBridge:
    """UDP socket for ExternalMedia RTP. Forwards ulaw audio via callbacks."""

    def __init__(self, host="127.0.0.1", port=20000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(0.5)
        self.remote_addr = None
        self.running = False
        self.packets_in = 0
        self.packets_out = 0
        self._seq = 0
        self._timestamp = 0
        self._ssrc = 0xABCD1234
        self.on_audio = None  # callback(ulaw_bytes)
        self._audio_queue = queue.Queue(maxsize=50)
        self._sender_thread = None

    def start(self):
        self.sock.bind((self.host, self.port))
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self._sender_thread.start()
        print(f"[RTP] Listening on {self.host}:{self.port}")

    def stop(self):
        self.running = False
        self._audio_queue.put(None)  # sentinel to stop sender thread
        if self._sender_thread and self._sender_thread.is_alive():
            self._sender_thread.join(timeout=2.0)
        self.sock.close()

    def flush_queue(self):
        """Discard all queued audio (call ended or barge-in)."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break
        print("[RTP] Audio queue flushed")

    def _loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                if self.remote_addr is None:
                    print(f"[RTP] First packet from {addr} — remote_addr set")
                self.remote_addr = addr
                self.packets_in += 1
                if len(data) < 12:
                    continue
                payload = data[12:]  # strip RTP header
                if self.on_audio:
                    self.on_audio(payload)
            except socket.timeout:
                continue
            except OSError:
                break

    def send_ulaw(self, ulaw_data: bytes):
        """Enqueue ulaw audio for sending. Non-blocking — returns immediately."""
        try:
            self._audio_queue.put_nowait(ulaw_data)
        except queue.Full:
            print(f"[RTP] Audio queue full, dropping {len(ulaw_data)} bytes")

    def _sender_loop(self):
        """Single dedicated sender thread — steady 20ms RTP pacing, no race conditions."""
        while True:
            ulaw_data = self._audio_queue.get()
            if ulaw_data is None:   # sentinel — stop requested
                break
            if not self.remote_addr:
                print(f"[RTP] _sender_loop: remote_addr not set, dropping {len(ulaw_data)} bytes")
                continue
            n_packets = len(ulaw_data) // 160 + (1 if len(ulaw_data) % 160 else 0)
            print(f"[RTP] Sending {len(ulaw_data)} bytes ({n_packets} packets) to {self.remote_addr}")
            start_time = time.monotonic()
            for i, offset in enumerate(range(0, len(ulaw_data), 160)):
                chunk = ulaw_data[offset:offset + 160]
                if len(chunk) < 160:
                    chunk += b'\x7f' * (160 - len(chunk))  # pad with ulaw silence

                self._seq = (self._seq + 1) & 0xFFFF
                self._timestamp = (self._timestamp + 160) & 0xFFFFFFFF

                header = struct.pack("!BBHII",
                    0x80, 0,  # V=2, PT=0 (ulaw)
                    self._seq, self._timestamp, self._ssrc)
                try:
                    self.sock.sendto(header + chunk, self.remote_addr)
                except OSError:
                    break
                self.packets_out += 1

                # Deadline-based pacing: self-corrects for OS scheduling jitter
                deadline = start_time + (i + 1) * 0.020
                sleep_for = deadline - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)


class ARIBridge:
    """ARI handler: originate → bridge → ExternalMedia. Minimal."""

    def __init__(self, host, port, user, password, app):
        self.base = f"http://{host}:{port}/ari"
        self.ws_url = f"ws://{host}:{port}/ari/events?api_key={user}:{password}&app={app}"
        self.auth = (user, password)
        self.app = app
        self.channel_id = None
        self.bridge_id = None
        self.ext_media_id = None
        self.call_start = None
        self._ws = None
        self.on_call_start = None
        self.on_call_end = None

    def _api(self, method, path, **kwargs):
        resp = requests.request(method, f"{self.base}{path}", auth=self.auth, timeout=10, **kwargs)
        if resp.status_code not in (200, 201, 204):
            print(f"[ARI] {method} {path} → {resp.status_code}: {resp.text[:200]}")
        return resp

    def originate(self, endpoint):
        resp = self._api("POST", "/channels", json={
            "endpoint": endpoint, "app": self.app, "callerId": "AI-Call"})
        return resp.status_code in (200, 201)

    def _setup_bridge(self, rtp_host, rtp_port):
        resp = self._api("POST", "/bridges", json={"type": "mixing"})
        if resp.status_code not in (200, 201):
            return False
        self.bridge_id = resp.json()["id"]
        self._api("POST", f"/bridges/{self.bridge_id}/addChannel",
                  json={"channel": self.channel_id})
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

    def _reset_call_state(self):
        self.channel_id = None
        self.bridge_id = None
        self.ext_media_id = None
        self.call_start = None

    def run_ws(self, mode, rtp_host, rtp_port, endpoint=None):
        """mode: 'outbound' | 'incoming' | 'both'"""

        def on_open(ws):
            print("[ARI] WebSocket connected")
            if mode in ("outbound", "both") and endpoint:
                threading.Thread(target=lambda: (
                    time.sleep(0.5),
                    print(f"[ARI] Originating: {endpoint}"),
                    self.originate(endpoint) and print("[ARI] Ringing...")
                ), daemon=True).start()
            else:
                print("[ARI] Waiting for incoming calls...")

        def on_message(ws, message):
            try:
                event = json.loads(message)
                etype = event.get("type", "")
                if etype == "StasisStart":
                    ch = event["channel"]
                    name = ch.get("name", "?")
                    state = ch.get("state", "?")
                    caller = ch.get("caller", {}).get("number", "unknown")
                    if self.channel_id is None and "UnicastRTP" not in name:
                        self.channel_id = ch["id"]
                        self.call_start = time.time()
                        is_incoming = (state != "Up")
                        print(f"[ARI] {'Incoming' if is_incoming else 'Outbound'}: {name} from={caller}")

                        def setup():
                            if is_incoming:
                                r = self._api("POST", f"/channels/{self.channel_id}/answer")
                                if r.status_code in (200, 204):
                                    print("[ARI] Answered incoming call")
                                time.sleep(0.3)  # let answer settle
                            if self._setup_bridge(rtp_host, rtp_port):
                                print("[ARI] Bridge ready")
                                if self.on_call_start:
                                    self.on_call_start(is_incoming, caller)

                        threading.Thread(target=setup, daemon=True).start()

                elif etype == "StasisEnd":
                    if event["channel"]["id"] == self.channel_id:
                        dur = time.time() - self.call_start if self.call_start else 0
                        print(f"[ARI] Call ended ({dur:.1f}s)")
                        self.cleanup()
                        self._reset_call_state()
                        if self.on_call_end:
                            self.on_call_end()
                        if mode == "outbound":
                            ws.close()
                        else:
                            print("[ARI] Ready for next call...")

                elif etype == "ChannelDtmfReceived":
                    digit = event.get("digit", "?")
                    print(f"[ARI] DTMF: {digit}")
                    if digit == "#":
                        self.hangup()
            except Exception as e:
                print(f"[ARI] Error: {e}")

        def on_error(ws, error):
            print(f"[ARI] WS error: {error}")

        def on_close(ws, code, reason):
            print("[ARI] WS closed")

        self._ws = ws_client.WebSocketApp(
            self.ws_url, on_open=on_open, on_message=on_message,
            on_error=on_error, on_close=on_close)
        self._ws.run_forever()


def main():
    parser = argparse.ArgumentParser(description="RPi Audio Bridge")
    parser.add_argument("--mode", default="outbound", choices=["outbound", "incoming", "both"],
                        help="outbound=originate only, incoming=accept calls, both=both")
    parser.add_argument("--endpoint", default=None, help="Outbound endpoint e.g. PJSIP/8757839258@1017 (required for outbound/both mode)")
    parser.add_argument("--server", required=True, help="AI server WebSocket URL e.g. ws://192.168.8.7:9090")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8088, type=int)
    parser.add_argument("--user", default="ari_user")
    parser.add_argument("--password", default="ari_pass")
    parser.add_argument("--rtp-host", default="127.0.0.1")
    parser.add_argument("--rtp-port", default=20000, type=int)
    parser.add_argument("--task-prompt", default="", help="Custom AI prompt for task calls (passed to ai_server)")
    args = parser.parse_args()

    if args.mode in ("outbound", "both") and not args.endpoint:
        print("ERROR: --endpoint required for outbound/both mode")
        sys.exit(1)

    print("=" * 55)
    print("  RPi AUDIO BRIDGE")
    print("=" * 55)
    print(f"  Mode      : {args.mode}")
    print(f"  Endpoint  : {args.endpoint or 'N/A (incoming only)'}")
    print(f"  AI Server : {args.server}")
    print("=" * 55)
    print()

    rtp = RTPBridge(args.rtp_host, args.rtp_port)
    ari = ARIBridge(args.host, args.port, args.user, args.password, "ai-call-app")

    # WebSocket to AI server
    ai_ws = None
    ai_connected = threading.Event()

    def connect_ai_server():
        nonlocal ai_ws

        def on_ai_open(ws):
            nonlocal ai_ws
            ai_ws = ws
            ai_connected.set()
            print(f"[AI-WS] Connected to {args.server}")

        def on_ai_message(ws, message):
            if isinstance(message, bytes):
                # AI response audio (ulaw) → enqueue for RTP sending (non-blocking)
                print(f"[AI-WS] Got audio: {len(message)} bytes, remote_addr={rtp.remote_addr}")
                rtp.send_ulaw(message)
            else:
                try:
                    data = json.loads(message)
                    if data.get("type") == "hangup":
                        print("[AI-WS] Task complete — hanging up")
                        ari.hangup()
                    else:
                        print(f"[AI-WS] Got text: {message[:80]}")
                except Exception:
                    print(f"[AI-WS] Got text: {message[:80]}")

        def on_ai_error(ws, error):
            print(f"[AI-WS] Error: {error}")

        def on_ai_close(ws, code, reason):
            print("[AI-WS] Disconnected")
            ai_connected.clear()

        ws = ws_client.WebSocketApp(
            args.server,
            on_open=on_ai_open,
            on_message=on_ai_message,
            on_error=on_ai_error,
            on_close=on_ai_close,
        )
        ws.run_forever()

    # Start AI server connection
    threading.Thread(target=connect_ai_server, daemon=True).start()
    print(f"[AI-WS] Connecting to {args.server}...")
    if not ai_connected.wait(timeout=10):
        print("[AI-WS] FAILED to connect to AI server. Is ai_server.py running?")
        sys.exit(1)

    # VAD gate on RPi — only speech-bracketed audio goes to PC
    def _send_json(obj):
        if ai_ws and ai_connected.is_set():
            try:
                ai_ws.send(json.dumps(obj))
            except Exception:
                pass

    def _send_ulaw(ulaw: bytes):
        if ai_ws and ai_connected.is_set():
            try:
                ai_ws.send(ulaw, opcode=0x2)  # binary
            except Exception:
                pass

    vad = silero_vad.VADGate(
        on_speech_start=lambda: _send_json({"type": "speech_start"}),
        on_speech_audio=_send_ulaw,
        on_speech_end=lambda: _send_json({"type": "speech_end"}),
    )

    def forward_audio(ulaw_payload):
        vad.feed(ulaw_payload)

    rtp.on_audio = forward_audio
    rtp.start()

    # ARI callbacks
    def on_call_start(is_incoming, caller):
        vad.reset()
        if ai_ws:
            ai_ws.send(json.dumps({
                "type": "call_start",
                "endpoint": args.endpoint or "incoming",
                "mode": "incoming" if is_incoming else "outbound",
                "caller": caller,
                "task_prompt": args.task_prompt or None,
            }))

    def on_call_end():
        # If we're mid-utterance, close the bracket so PC flushes its buffer
        if vad.is_speaking():
            _send_json({"type": "speech_end"})
        vad.reset()
        rtp.flush_queue()  # discard any queued audio for ended call
        if ai_ws:
            ai_ws.send(json.dumps({"type": "call_end"}))

    ari.on_call_start = on_call_start
    ari.on_call_end = on_call_end

    # Run ARI (blocks until WS closes — for incoming mode, runs forever)
    try:
        ari.run_ws(args.mode, args.rtp_host, args.rtp_port, endpoint=args.endpoint)
    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted")
        ari.hangup()
        ari.cleanup()

    rtp.stop()
    print()
    print("=" * 55)
    print(f"  RTP in: {rtp.packets_in}  out: {rtp.packets_out}")
    print("=" * 55)


if __name__ == "__main__":
    main()
