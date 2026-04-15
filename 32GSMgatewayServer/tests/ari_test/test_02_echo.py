#!/usr/bin/env python3
"""
Phase 2 — ExternalMedia Audio Echo Test
Proves bidirectional audio streaming works via ARI + ExternalMedia.

Creates a Local channel → Stasis app → mixing bridge → ExternalMedia.
Echoes received RTP audio back to the caller.

For a real call test, use --endpoint flag:
    python3 test_02_echo.py --endpoint "PJSIP/9876543210@1001"

Usage:
    python3 test_02_echo.py                          # Local channel (no real call)
    python3 test_02_echo.py --endpoint PJSIP/NUM@1001  # Real GSM call
"""

import argparse
import json
import socket
import struct
import sys
import threading
import time

import requests
import websocket


class RTPEchoServer:
    """Simple UDP server that echoes RTP packets back with corrected headers."""

    def __init__(self, host="127.0.0.1", port=20000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(1.0)
        self.running = False
        self.packets_in = 0
        self.packets_out = 0
        self.remote_addr = None
        # Outbound RTP state
        self.seq = 0
        self.timestamp = 0
        self.ssrc = 0x12345678

    def start(self):
        self.sock.bind((self.host, self.port))
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        print(f"[RTP] Echo server listening on {self.host}:{self.port}")

    def stop(self):
        self.running = False
        self.sock.close()

    def _loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                self.remote_addr = addr
                self.packets_in += 1

                if len(data) < 12:
                    continue

                # Parse incoming RTP header
                # Byte 0: V(2) P(1) X(1) CC(4)
                # Byte 1: M(1) PT(7)
                # Bytes 2-3: Sequence number
                # Bytes 4-7: Timestamp
                # Bytes 8-11: SSRC
                payload = data[12:]  # Strip RTP header

                # Build outbound RTP header with our own seq/timestamp/ssrc
                self.seq = (self.seq + 1) & 0xFFFF
                # ulaw: 1 byte/sample, slin: 2 bytes/sample
                # Use incoming timestamp increment to stay in sync
                incoming_ts = struct.unpack("!I", data[4:8])[0]
                if not hasattr(self, '_last_in_ts'):
                    self._last_in_ts = incoming_ts
                    self._ts_delta = len(payload)  # fallback
                else:
                    self._ts_delta = (incoming_ts - self._last_in_ts) & 0xFFFFFFFF
                    self._last_in_ts = incoming_ts
                self.timestamp = (self.timestamp + self._ts_delta) & 0xFFFFFFFF
                pt = data[1] & 0x7F  # Preserve payload type

                header = struct.pack("!BBHII",
                    0x80,           # V=2, P=0, X=0, CC=0
                    pt,             # M=0, PT=same as incoming
                    self.seq,
                    self.timestamp & 0xFFFFFFFF,
                    self.ssrc,
                )

                self.sock.sendto(header + payload, addr)
                self.packets_out += 1

                if self.packets_in % 500 == 0:
                    print(f"[RTP] {self.packets_in} packets received, {self.packets_out} sent back")

            except socket.timeout:
                continue
            except OSError:
                break


class ARIEchoTest:
    """ARI handler: originates call, creates bridge + ExternalMedia, manages lifecycle."""

    def __init__(self, host, port, user, password, app, endpoint, rtp_host, rtp_port, fmt="ulaw"):
        self.base = f"http://{host}:{port}/ari"
        self.ws_url = f"ws://{host}:{port}/ari/events?api_key={user}:{password}&app={app}"
        self.auth = (user, password)
        self.app = app
        self.endpoint = endpoint
        self.rtp_host = rtp_host
        self.rtp_port = rtp_port
        self.fmt = fmt

        self.caller_channel_id = None
        self.ext_media_channel_id = None
        self.bridge_id = None
        self.ws = None
        self.events_received = []
        self.call_start = None
        self.call_end = None

    def run(self):
        print(f"[ARI] Connecting WebSocket: {self.ws_url}")

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever()

    def _on_open(self, ws):
        print("[ARI] WebSocket connected")
        # Originate call in a separate thread so WS keeps receiving
        threading.Thread(target=self._originate, daemon=True).start()

    def _on_message(self, ws, message):
        try:
            self._handle_message(message)
        except Exception as e:
            print(f"[ARI] ERROR in handler: {e}")
            import traceback
            traceback.print_exc()

    def _handle_message(self, message):
        event = json.loads(message)
        event_type = event.get("type", "unknown")
        self.events_received.append(event_type)
        print(f"[ARI] Event: {event_type}")

        if event_type == "StasisStart":
            channel = event["channel"]
            channel_id = channel["id"]
            channel_name = channel.get("name", "?")
            channel_state = channel.get("state", "?")
            print(f"[ARI] StasisStart: {channel_name} state={channel_state} id={channel_id[:20]}...")

            # First StasisStart = our originated channel (caller)
            if self.caller_channel_id is None:
                self.caller_channel_id = channel_id
                self.call_start = time.time()
                threading.Thread(target=self._setup_bridge, daemon=True).start()
            # ExternalMedia channel enters Stasis — already added to bridge in _setup_bridge
            # Do NOT add again here (double-add causes LeftBridge/EnteredBridge cycle)

        elif event_type == "ChannelStateChange":
            state = event["channel"].get("state", "?")
            channel_id = event["channel"]["id"]
            print(f"[ARI] ChannelState: {channel_id[:20]}... → {state}")
            # For outbound calls: if we haven't set up bridge yet and channel is Up
            if state == "Up" and channel_id == self.caller_channel_id and not self.bridge_id:
                print("[ARI] Call answered — setting up bridge")
                threading.Thread(target=self._setup_bridge, daemon=True).start()

        elif event_type == "StasisEnd":
            channel_id = event["channel"]["id"]
            print(f"[ARI] StasisEnd: {channel_id[:20]}...")
            if channel_id == self.caller_channel_id:
                self.call_end = time.time()
                duration = (self.call_end - self.call_start) if self.call_start else 0
                print(f"[ARI] Caller hung up — duration={duration:.1f}s — cleaning up")
                self._cleanup()

        elif event_type == "ChannelDtmfReceived":
            digit = event.get("digit", "?")
            print(f"[ARI] DTMF: {digit} (press # to hang up)")
            if digit == "#":
                print("[ARI] # pressed — hanging up")
                if self.caller_channel_id:
                    requests.delete(f"{self.base}/channels/{self.caller_channel_id}",
                                    auth=self.auth, timeout=5)

        elif event_type == "ChannelHangupRequest":
            print(f"[ARI] Remote hangup requested")

    def _on_error(self, ws, error):
        print(f"[ARI] WebSocket error: {error}")

    def _on_close(self, ws, code, reason):
        print(f"[ARI] WebSocket closed: code={code} reason={reason}")

    def _originate(self):
        """Originate a channel into the Stasis app."""
        time.sleep(0.5)  # Let WS stabilize
        print(f"[ARI] Originating: endpoint={self.endpoint}")

        resp = requests.post(
            f"{self.base}/channels",
            auth=self.auth,
            json={
                "endpoint": self.endpoint,
                "app": self.app,
                "callerId": "ARI-Echo-Test",
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            print(f"[ARI] Originate OK: channel={data.get('id', '?')}")
        else:
            print(f"[ARI] Originate FAILED: {resp.status_code} {resp.text[:200]}")
            self._cleanup()

    def _setup_bridge(self):
        """Create mixing bridge, add caller, create ExternalMedia, add it too."""
        time.sleep(0.3)

        # 1. Create bridge
        print("[ARI] Creating mixing bridge...")
        resp = requests.post(
            f"{self.base}/bridges",
            auth=self.auth,
            json={"type": "mixing", "name": "echo-test-bridge"},
            timeout=5,
        )
        if resp.status_code not in (200, 201):
            print(f"[ARI] Bridge create FAILED: {resp.status_code} {resp.text[:200]}")
            return
        self.bridge_id = resp.json()["id"]
        print(f"[ARI] Bridge created: {self.bridge_id}")

        # 2. Add caller channel to bridge
        self._add_to_bridge(self.caller_channel_id)

        # 3. Create ExternalMedia channel
        print(f"[ARI] Creating ExternalMedia -> {self.rtp_host}:{self.rtp_port} format={self.fmt}")
        resp = requests.post(
            f"{self.base}/channels/externalMedia",
            auth=self.auth,
            json={
                "app": self.app,
                "external_host": f"{self.rtp_host}:{self.rtp_port}",
                "format": self.fmt,
                "encapsulation": "rtp",
                "transport": "udp",
                "direction": "both",
            },
            timeout=5,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            self.ext_media_channel_id = data["id"]
            print(f"[ARI] ExternalMedia created: {self.ext_media_channel_id}")
            # Add ExternalMedia to bridge
            self._add_to_bridge(self.ext_media_channel_id)
        else:
            print(f"[ARI] ExternalMedia FAILED: {resp.status_code} {resp.text[:300]}")

    def _add_to_bridge(self, channel_id):
        if not self.bridge_id:
            return
        resp = requests.post(
            f"{self.base}/bridges/{self.bridge_id}/addChannel",
            auth=self.auth,
            json={"channel": channel_id},
            timeout=5,
        )
        if resp.status_code in (200, 204):
            print(f"[ARI] Added channel {channel_id[:20]}... to bridge")
        else:
            print(f"[ARI] addChannel FAILED: {resp.status_code} {resp.text[:200]}")

    def _cleanup(self):
        """Destroy bridge and hang up channels."""
        if self.bridge_id:
            requests.delete(f"{self.base}/bridges/{self.bridge_id}", auth=self.auth, timeout=5)
            print(f"[ARI] Bridge {self.bridge_id} destroyed")
        if self.ext_media_channel_id:
            requests.delete(f"{self.base}/channels/{self.ext_media_channel_id}", auth=self.auth, timeout=5)
        # Close WebSocket
        if self.ws:
            self.ws.close()


def main():
    parser = argparse.ArgumentParser(description="ARI ExternalMedia Echo Test")
    parser.add_argument("--host", default="localhost", help="Asterisk host")
    parser.add_argument("--port", default=8088, type=int, help="ARI HTTP port")
    parser.add_argument("--user", default="ari_user")
    parser.add_argument("--password", default="ari_pass")
    parser.add_argument("--app", default="ai-call-app")
    parser.add_argument("--endpoint", default="Local/s@stasis-test",
                        help="Channel endpoint. Use PJSIP/NUMBER@1001 for real call")
    parser.add_argument("--rtp-host", default="127.0.0.1", help="RTP echo server bind address")
    parser.add_argument("--rtp-port", default=20000, type=int, help="RTP echo server port")
    parser.add_argument("--format", default="ulaw", help="ExternalMedia format: ulaw, slin, slin16")
    args = parser.parse_args()

    # Start RTP echo server
    rtp = RTPEchoServer(args.rtp_host, args.rtp_port)
    rtp.start()

    # Start ARI test
    ari = ARIEchoTest(
        host=args.host, port=args.port,
        user=args.user, password=args.password,
        app=args.app, endpoint=args.endpoint,
        rtp_host=args.rtp_host, rtp_port=args.rtp_port,
        fmt=args.format,
    )

    try:
        ari.run()
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user")
    finally:
        rtp.stop()
        print()
        print("=" * 60)
        print(f"  RTP packets received : {rtp.packets_in}")
        print(f"  RTP packets sent     : {rtp.packets_out}")
        print(f"  ARI events received  : {len(ari.events_received)}")
        print(f"  Event types          : {', '.join(dict.fromkeys(ari.events_received))}")
        if rtp.packets_in > 0 and rtp.packets_out > 0:
            print(f"  Result               : PASS — bidirectional audio confirmed")
        else:
            print(f"  Result               : FAIL — no RTP packets")
        print("=" * 60)


if __name__ == "__main__":
    main()
