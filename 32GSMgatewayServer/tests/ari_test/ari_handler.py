"""
ARI Handler — Manages ARI WebSocket events, call lifecycle, bridges, and ExternalMedia.

Responsibilities:
  - Connect to ARI WebSocket for Stasis events
  - Originate calls (Local or PJSIP)
  - Create mixing bridge + ExternalMedia channel on StasisStart
  - Cleanup on hangup
  - Emit lifecycle callbacks for the pipeline
"""

import asyncio
import json
import logging

import requests
import websocket

log = logging.getLogger(__name__)


class ARIHandler:
    """Manages a single AI call via ARI."""

    def __init__(self, config: dict):
        ari = config["ari"]
        rtp = config["rtp"]
        self.host = ari["host"]
        self.port = ari["port"]
        self.user = ari["username"]
        self.password = ari["password"]
        self.app = ari["app"]
        self.base = f"http://{self.host}:{self.port}/ari"
        self.auth = (self.user, self.password)
        self.rtp_host = rtp["listen_host"]
        self.rtp_port = rtp["listen_port"]

        self.caller_channel_id = None
        self.ext_media_channel_id = None
        self.bridge_id = None

        # Callbacks
        self.on_call_start = None      # async callable(channel_id)
        self.on_call_end = None        # async callable(channel_id)
        self.on_dtmf = None            # async callable(digit)

        self._ws = None
        self._loop = None
        self._connected = asyncio.Event()

    def _api(self, method, path, **kwargs):
        """Sync REST call to ARI."""
        url = f"{self.base}{path}"
        resp = requests.request(method, url, auth=self.auth, timeout=10, **kwargs)
        if resp.status_code not in (200, 201, 204):
            log.error("ARI %s %s -> %s: %s", method, path, resp.status_code, resp.text[:300])
        return resp

    def originate(self, endpoint: str, caller_id: str = "AI-Call"):
        """Originate a channel into this Stasis app."""
        log.info("Originating: endpoint=%s", endpoint)
        resp = self._api("POST", "/channels", json={
            "endpoint": endpoint,
            "app": self.app,
            "callerId": caller_id,
        })
        if resp.status_code in (200, 201):
            return resp.json()
        return None

    def _create_bridge(self):
        resp = self._api("POST", "/bridges", json={
            "type": "mixing",
            "name": f"ai-bridge-{self.caller_channel_id[:8]}",
        })
        if resp.status_code in (200, 201):
            self.bridge_id = resp.json()["id"]
            log.info("Bridge created: %s", self.bridge_id)
            return True
        return False

    def _add_channel_to_bridge(self, channel_id):
        if not self.bridge_id:
            return
        self._api("POST", f"/bridges/{self.bridge_id}/addChannel",
                  json={"channel": channel_id})
        log.info("Channel %s added to bridge", channel_id[:20])

    def _create_external_media(self):
        log.info("Creating ExternalMedia -> %s:%s", self.rtp_host, self.rtp_port)
        resp = self._api("POST", "/channels/externalMedia", json={
            "app": self.app,
            "external_host": f"{self.rtp_host}:{self.rtp_port}",
            "format": "slin16",
            "encapsulation": "rtp",
            "transport": "udp",
            "direction": "both",
        })
        if resp.status_code in (200, 201):
            self.ext_media_channel_id = resp.json()["id"]
            log.info("ExternalMedia created: %s", self.ext_media_channel_id)
            return True
        return False

    def _setup_call(self):
        """Create bridge + ExternalMedia and wire everything together."""
        if not self._create_bridge():
            return
        self._add_channel_to_bridge(self.caller_channel_id)
        if self._create_external_media():
            self._add_channel_to_bridge(self.ext_media_channel_id)

    def cleanup(self):
        """Destroy bridge and hang up ExternalMedia channel."""
        if self.bridge_id:
            self._api("DELETE", f"/bridges/{self.bridge_id}")
            log.info("Bridge destroyed")
            self.bridge_id = None
        if self.ext_media_channel_id:
            self._api("DELETE", f"/channels/{self.ext_media_channel_id}")
            self.ext_media_channel_id = None

    def hangup_caller(self):
        """Hang up the caller channel."""
        if self.caller_channel_id:
            self._api("DELETE", f"/channels/{self.caller_channel_id}",
                      params={"reason_code": 16})

    # --- WebSocket event handling ---

    def _handle_event(self, event: dict):
        event_type = event.get("type", "")

        if event_type == "StasisStart":
            channel_id = event["channel"]["id"]
            channel_name = event["channel"].get("name", "?")
            log.info("StasisStart: %s (%s)", channel_name, channel_id[:20])

            if self.caller_channel_id is None:
                self.caller_channel_id = channel_id
                self._setup_call()
                if self.on_call_start and self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self.on_call_start(channel_id), self._loop)

        elif event_type == "StasisEnd":
            channel_id = event["channel"]["id"]
            log.info("StasisEnd: %s", channel_id[:20])
            if channel_id == self.caller_channel_id:
                self.cleanup()
                if self.on_call_end and self._loop:
                    asyncio.run_coroutine_threadsafe(
                        self.on_call_end(channel_id), self._loop)
                if self._ws:
                    self._ws.close()

        elif event_type == "ChannelDtmfReceived":
            digit = event.get("digit", "?")
            log.info("DTMF: %s", digit)
            if self.on_dtmf and self._loop:
                asyncio.run_coroutine_threadsafe(
                    self.on_dtmf(digit), self._loop)

        elif event_type == "ChannelStateChange":
            state = event["channel"].get("state", "?")
            log.info("ChannelState: %s -> %s", event["channel"]["id"][:20], state)

    def run_ws(self, loop: asyncio.AbstractEventLoop):
        """Run ARI WebSocket in a thread. Pass the asyncio loop for callbacks."""
        self._loop = loop
        ws_url = (f"ws://{self.host}:{self.port}/ari/events"
                  f"?api_key={self.user}:{self.password}&app={self.app}")

        def on_open(ws):
            log.info("ARI WebSocket connected")
            self._connected.set()

        def on_message(ws, msg):
            try:
                self._handle_event(json.loads(msg))
            except Exception as e:
                log.error("Event handler error: %s", e)

        def on_error(ws, err):
            log.error("ARI WebSocket error: %s", err)

        def on_close(ws, code, reason):
            log.info("ARI WebSocket closed: code=%s reason=%s", code, reason)

        self._ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        self._ws.run_forever()

    async def wait_connected(self, timeout=10):
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
