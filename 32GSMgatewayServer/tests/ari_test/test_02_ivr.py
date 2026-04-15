#!/usr/bin/env python3
"""
Phase 2 — Pre-Recorded IVR Call via ARI
Replaces the entire dialplan IVR with pure Python + ARI REST/WebSocket.

Usage:
    python3 test_02_ivr.py                                          # Local channel test
    python3 test_02_ivr.py --endpoint "PJSIP/8757839258@1017"       # Real GSM call
    python3 test_02_ivr.py --endpoint "PJSIP/NUM@1017" --intro "sound:/var/lib/asterisk/sounds/hi/static/01_Namskar"
"""

import argparse
import json
import sys
import threading
import time
from enum import Enum

import requests
import websocket


class IVRState(Enum):
    IDLE = "idle"
    RINGING = "ringing"
    PLAYING_INTRO = "playing_intro"
    PLAYING_MENU = "playing_menu"
    WAITING_DTMF = "waiting_dtmf"
    PLAYING_RESPONSE = "playing_response"
    DONE = "done"


class ARIIvrTest:
    """Simple IVR call via ARI: originate → play audio → collect DTMF → hangup."""

    def __init__(self, args):
        self.host = args.host
        self.port = args.port
        self.user = args.user
        self.password = args.password
        self.app = args.app
        self.endpoint = args.endpoint

        self.base = f"http://{self.host}:{self.port}/ari"
        self.auth = (self.user, self.password)

        # Audio clips
        self.snd_intro = args.intro
        self.snd_menu = args.menu
        self.snd_success = args.success
        self.snd_cancel = args.cancel
        self.snd_error = args.error
        self.snd_timeout = args.timeout_sound

        # State
        self.state = IVRState.IDLE
        self.channel_id = None
        self.current_playback_id = None
        self.dtmf_received = None
        self.dtmf_at_state = None
        self.menu_retries = 0
        self.max_retries = 3
        self.dtmf_timeout = args.dtmf_timeout
        self.events = []
        self.call_start = None
        self.call_end = None
        self._ws = None
        self._dtmf_timer = None

    def _set_state(self, new_state):
        old = self.state
        self.state = new_state
        print(f"[IVR] {old.value} → {new_state.value}")

    # --- ARI REST helpers ---

    def _api(self, method, path, **kwargs):
        url = f"{self.base}{path}"
        try:
            resp = requests.request(method, url, auth=self.auth, timeout=10, **kwargs)
            if resp.status_code not in (200, 201, 204):
                print(f"[ARI] {method} {path} → {resp.status_code}: {resp.text[:200]}")
            return resp
        except Exception as e:
            print(f"[ARI] {method} {path} → ERROR: {e}")
            return None

    def _play(self, media):
        """Play audio on the channel. Returns playback ID."""
        resp = self._api("POST", f"/channels/{self.channel_id}/play",
                         json={"media": media})
        if resp and resp.status_code in (200, 201):
            pb_id = resp.json().get("id", "")
            self.current_playback_id = pb_id
            print(f"[ARI] Playing: {media} (playback={pb_id[:12]}...)")
            return pb_id
        return None

    def _stop_playback(self):
        """Stop current playback if any."""
        if self.current_playback_id:
            self._api("DELETE", f"/playbacks/{self.current_playback_id}")
            self.current_playback_id = None

    def _hangup(self):
        """Hang up the channel."""
        if self.channel_id:
            self._api("DELETE", f"/channels/{self.channel_id}")
            print("[ARI] Hangup sent")

    # --- DTMF timeout ---

    def _start_dtmf_timer(self):
        self._cancel_dtmf_timer()
        self._dtmf_timer = threading.Timer(self.dtmf_timeout, self._on_dtmf_timeout)
        self._dtmf_timer.daemon = True
        self._dtmf_timer.start()

    def _cancel_dtmf_timer(self):
        if self._dtmf_timer:
            self._dtmf_timer.cancel()
            self._dtmf_timer = None

    def _on_dtmf_timeout(self):
        if self.state not in (IVRState.WAITING_DTMF, IVRState.PLAYING_MENU):
            return
        self.menu_retries += 1
        print(f"[IVR] No DTMF — timeout (retry {self.menu_retries}/{self.max_retries})")
        if self.menu_retries >= self.max_retries:
            self._set_state(IVRState.PLAYING_RESPONSE)
            self._play(self.snd_timeout)
        else:
            # Replay menu
            self._set_state(IVRState.PLAYING_MENU)
            self._play(self.snd_menu)

    # --- IVR logic ---

    def _handle_stasis_start(self, event):
        channel = event["channel"]
        self.channel_id = channel["id"]
        channel_name = channel.get("name", "?")
        channel_state = channel.get("state", "?")
        self.call_start = time.time()
        print(f"[ARI] StasisStart: {channel_name} state={channel_state} (id={self.channel_id[:20]}...)")

        if channel_state == "Up":
            # Outbound call already answered by remote — play immediately
            self._set_state(IVRState.PLAYING_INTRO)
            self._play(self.snd_intro)
        else:
            # Channel still ringing — wait for ChannelStateChange to "Up"
            self._set_state(IVRState.RINGING)
            print("[IVR] Waiting for remote to answer...")

    def _handle_playback_finished(self, event):
        pb_id = event.get("playback", {}).get("id", "")

        if self.state == IVRState.PLAYING_INTRO:
            # Intro done → play menu
            self._set_state(IVRState.PLAYING_MENU)
            self._play(self.snd_menu)

        elif self.state == IVRState.PLAYING_MENU:
            # Menu done → wait for DTMF
            self._set_state(IVRState.WAITING_DTMF)
            self._start_dtmf_timer()

        elif self.state == IVRState.PLAYING_RESPONSE:
            # Response done → hangup
            self._set_state(IVRState.DONE)
            self._hangup()

    def _handle_dtmf(self, event):
        digit = event.get("digit", "?")
        print(f"[ARI] DTMF received: {digit}")
        self._cancel_dtmf_timer()

        if self.state not in (IVRState.PLAYING_MENU, IVRState.WAITING_DTMF):
            print(f"[IVR] Ignoring DTMF in state {self.state.value}")
            return

        self.dtmf_received = digit
        self.dtmf_at_state = self.state.value
        self._stop_playback()

        if digit == "1":
            print("[IVR] → ACCEPTED")
            self._set_state(IVRState.PLAYING_RESPONSE)
            self._play(self.snd_success)

        elif digit == "2":
            print("[IVR] → CANCELLED")
            self._set_state(IVRState.PLAYING_RESPONSE)
            self._play(self.snd_cancel)

        else:
            print(f"[IVR] → Wrong key ({digit}), replaying menu")
            self.menu_retries += 1
            if self.menu_retries >= self.max_retries:
                self._set_state(IVRState.PLAYING_RESPONSE)
                self._play(self.snd_timeout)
            else:
                self._play(self.snd_error)
                # After error sound, replay menu
                # We'll handle this by going back to PLAYING_INTRO logic
                # Actually: set state to PLAYING_MENU so PlaybackFinished replays
                self._set_state(IVRState.PLAYING_INTRO)  # trick: next PBFinished → play menu

    def _handle_stasis_end(self, event):
        self.call_end = time.time()
        self._cancel_dtmf_timer()
        print(f"[ARI] StasisEnd")
        self._print_result()
        if self._ws:
            self._ws.close()

    # --- Result ---

    def _print_result(self):
        duration = (self.call_end - self.call_start) if (self.call_start and self.call_end) else 0
        result = "NO_DTMF"
        if self.dtmf_received == "1":
            result = "ACCEPTED"
        elif self.dtmf_received == "2":
            result = "CANCELLED"
        elif self.dtmf_received:
            result = f"WRONG_KEY({self.dtmf_received})"

        print()
        print("=" * 50)
        print("  IVR CALL RESULT")
        print("=" * 50)
        print(f"  Endpoint       : {self.endpoint}")
        print(f"  Channel ID     : {self.channel_id or 'N/A'}")
        print(f"  Duration       : {duration:.1f}s")
        print(f"  DTMF Received  : {self.dtmf_received or 'none'}")
        print(f"  DTMF at State  : {self.dtmf_at_state or 'N/A'}")
        print(f"  Menu Retries   : {self.menu_retries}")
        print(f"  Result         : {result}")
        print(f"  Events         : {', '.join(dict.fromkeys(self.events))}")
        print("=" * 50)

    # --- WebSocket ---

    def _on_open(self, ws):
        print("[ARI] WebSocket connected")
        # Originate in separate thread
        threading.Thread(target=self._originate, daemon=True).start()

    def _on_message(self, ws, message):
        try:
            self._handle_message(message)
        except Exception as e:
            print(f"[ARI] ERROR in message handler: {e}")
            import traceback
            traceback.print_exc()

    def _handle_message(self, message):
        event = json.loads(message)
        event_type = event.get("type", "")
        self.events.append(event_type)
        print(f"[ARI] Event: {event_type}")

        if event_type == "StasisStart":
            self._handle_stasis_start(event)

        elif event_type == "PlaybackFinished":
            self._handle_playback_finished(event)

        elif event_type == "ChannelDtmfReceived":
            self._handle_dtmf(event)

        elif event_type == "StasisEnd":
            self._handle_stasis_end(event)

        elif event_type == "ChannelStateChange":
            state = event.get("channel", {}).get("state", "?")
            channel_id = event.get("channel", {}).get("id", "")
            print(f"[ARI] ChannelState → {state}")
            # Remote answered — start IVR
            if state == "Up" and channel_id == self.channel_id and self.state == IVRState.RINGING:
                print("[IVR] Remote answered!")
                self._set_state(IVRState.PLAYING_INTRO)
                self._play(self.snd_intro)

        elif event_type == "ChannelDestroyed":
            pass  # Normal after hangup

        elif event_type == "PlaybackStarted":
            pass  # Info only

        elif event_type == "ChannelHangupRequest":
            print("[ARI] Remote hangup requested")

    def _on_error(self, ws, error):
        print(f"[ARI] WebSocket error: {error}")

    def _on_close(self, ws, code, reason):
        print(f"[ARI] WebSocket closed (code={code})")

    def _originate(self):
        time.sleep(0.5)
        print(f"[ARI] Originating: {self.endpoint}")
        self._set_state(IVRState.RINGING)
        resp = self._api("POST", "/channels", json={
            "endpoint": self.endpoint,
            "app": self.app,
            "callerId": "IVR-Test",
        })
        if resp and resp.status_code in (200, 201):
            print(f"[ARI] Originate OK — waiting for answer...")
        else:
            print("[ARI] Originate FAILED")
            if self._ws:
                self._ws.close()

    def run(self):
        ws_url = (f"ws://{self.host}:{self.port}/ari/events"
                  f"?api_key={self.user}:{self.password}&app={self.app}")
        print(f"[ARI] Connecting: {ws_url}")

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws.run_forever()


def main():
    parser = argparse.ArgumentParser(description="ARI Pre-Recorded IVR Call Test")

    # ARI connection
    parser.add_argument("--host", default="localhost", help="Asterisk host")
    parser.add_argument("--port", default=8088, type=int, help="ARI HTTP port")
    parser.add_argument("--user", default="ari_user", help="ARI username")
    parser.add_argument("--password", default="ari_pass", help="ARI password")
    parser.add_argument("--app", default="ai-call-app", help="Stasis app name")

    # Call target
    parser.add_argument("--endpoint", default="Local/s@stasis-test",
                        help="SIP endpoint (e.g. PJSIP/8757839258@1017)")

    # Audio clips (Asterisk built-in sounds as defaults)
    parser.add_argument("--intro", default="sound:hello-world",
                        help="Intro audio (played first)")
    parser.add_argument("--menu", default="sound:agent-login-with",
                        help="Menu audio (press 1 or 2)")
    parser.add_argument("--success", default="sound:auth-thankyou",
                        help="Success audio (DTMF 1)")
    parser.add_argument("--cancel", default="sound:vm-goodbye",
                        help="Cancel audio (DTMF 2)")
    parser.add_argument("--error", default="sound:pbx-invalid",
                        help="Wrong key audio")
    parser.add_argument("--timeout-sound", default="sound:vm-goodbye",
                        help="Timeout audio (no DTMF)")

    # Behavior
    parser.add_argument("--dtmf-timeout", default=10, type=int,
                        help="Seconds to wait for DTMF after menu")

    args = parser.parse_args()

    print("=" * 50)
    print("  ARI IVR TEST")
    print("=" * 50)
    print(f"  Endpoint  : {args.endpoint}")
    print(f"  ARI       : {args.host}:{args.port}")
    print(f"  App       : {args.app}")
    print(f"  Intro     : {args.intro}")
    print(f"  Menu      : {args.menu}")
    print("=" * 50)
    print()

    test = ARIIvrTest(args)
    try:
        test.run()
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted")
        test._hangup()
        test._print_result()


if __name__ == "__main__":
    main()
