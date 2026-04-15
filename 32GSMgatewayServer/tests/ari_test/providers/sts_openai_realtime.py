"""
OpenAI Realtime STS Provider — Speech-to-Speech via OpenAI Realtime API.

Audio format:
  - ExternalMedia: slin16 (16kHz, 16-bit LE PCM)
  - OpenAI Realtime: 24kHz, 16-bit LE PCM
  - Need: upsample 16→24kHz on input, downsample 24→16kHz on output
"""

import asyncio
import audioop
import base64
import json
import logging
from typing import AsyncIterator

import websocket

from providers.base import BaseSTS

log = logging.getLogger(__name__)

OPENAI_RATE = 24000
TARGET_RATE = 16000


class OpenAIRealtimeSTS(BaseSTS):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gpt-4o-realtime-preview")
        self.voice = config.get("voice", "alloy")
        self._ws = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._running = False
        self._ws_thread = None
        self._loop = None

    async def start(self, system_prompt: str = ""):
        self._running = True
        self._loop = asyncio.get_event_loop()

        url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        headers = [
            f"Authorization: Bearer {self.api_key}",
            "OpenAI-Beta: realtime=v1",
        ]

        self._ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=lambda ws: self._on_open(ws, system_prompt),
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )

        import threading
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever, daemon=True)
        self._ws_thread.start()

        # Wait for connection
        await asyncio.sleep(1)
        log.info("OpenAI Realtime started (model=%s, voice=%s)", self.model, self.voice)

    async def stop(self):
        self._running = False
        if self._ws:
            self._ws.close()
        log.info("OpenAI Realtime stopped")

    def _on_open(self, ws, system_prompt):
        # Configure session
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "instructions": system_prompt or
                    "You are a helpful voice assistant. Keep responses concise.",
                "voice": self.voice,
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.5,
                    "prefix_padding_ms": 300,
                    "silence_duration_ms": 500,
                },
            },
        }
        ws.send(json.dumps(config))
        log.info("OpenAI Realtime session configured")

    def _on_message(self, ws, message):
        try:
            event = json.loads(message)
            event_type = event.get("type", "")

            if event_type == "response.audio.delta":
                # Base64 PCM at 24kHz
                audio_b64 = event.get("delta", "")
                if audio_b64:
                    pcm_24k = base64.b64decode(audio_b64)
                    # Downsample 24kHz → 16kHz
                    pcm_16k, _ = audioop.ratecv(
                        pcm_24k, 2, 1, OPENAI_RATE, TARGET_RATE, None)
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self._response_queue.put(pcm_16k), self._loop)

            elif event_type == "response.audio_transcript.done":
                transcript = event.get("transcript", "")
                log.info("AI said: %s", transcript)

            elif event_type == "input_audio_buffer.speech_started":
                log.info("User speech detected")

            elif event_type == "error":
                log.error("OpenAI Realtime error: %s", event)

        except Exception as e:
            log.error("OpenAI Realtime message error: %s", e)

    def _on_error(self, ws, error):
        log.error("OpenAI Realtime WS error: %s", error)

    def _on_close(self, ws, code, reason):
        log.info("OpenAI Realtime WS closed: %s %s", code, reason)

    async def feed_audio(self, pcm_chunk: bytes):
        if not self._ws or not self._running:
            return
        # Upsample 16kHz → 24kHz
        pcm_24k, _ = audioop.ratecv(
            pcm_chunk, 2, 1, TARGET_RATE, OPENAI_RATE, None)
        # Send as base64
        msg = json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm_24k).decode(),
        })
        try:
            self._ws.send(msg)
        except Exception as e:
            log.error("OpenAI feed_audio error: %s", e)

    async def audio_responses(self) -> AsyncIterator[bytes]:
        while self._running:
            try:
                pcm = await asyncio.wait_for(
                    self._response_queue.get(), timeout=0.1)
                yield pcm
            except asyncio.TimeoutError:
                continue
