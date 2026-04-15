"""
Gemini Live STS Provider — Speech-to-Speech via Google Gemini Live API.

Audio format match:
  - ExternalMedia outputs slin16 (16kHz, 16-bit LE PCM)
  - Gemini Live accepts 16kHz PCM natively → zero resampling on input
  - Gemini Live outputs 24kHz PCM → downsample to 16kHz for ExternalMedia

Uses the google-genai SDK with Live API (WebSocket-based bidirectional streaming).
"""

import asyncio
import audioop
import base64
import json
import logging
import struct
from typing import AsyncIterator

from providers.base import BaseSTS

log = logging.getLogger(__name__)

# Gemini Live outputs 24kHz, ExternalMedia wants 16kHz
GEMINI_OUTPUT_RATE = 24000
TARGET_RATE = 16000


class GeminiLiveSTS(BaseSTS):
    """Gemini Live API speech-to-speech provider."""

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gemini-2.5-flash")
        self.voice = config.get("voice", "Aoede")  # Gemini voice name
        self.language = config.get("language", "hi")
        self._client = None
        self._session = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._running = False
        self._receive_task = None

    async def start(self, system_prompt: str = ""):
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise ImportError("Install google-genai: pip install google-genai")

        self._client = genai.Client(api_key=self.api_key)

        # Configure Live API session
        live_config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice,
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=system_prompt or
                    f"You are a helpful voice assistant. Respond in {self.language}. "
                    "Keep responses concise and conversational.")]
            ),
        )

        self._session = await self._client.aio.live.connect(
            model=self.model,
            config=live_config,
        )
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
        log.info("Gemini Live session started (model=%s, voice=%s)", self.model, self.voice)

    async def stop(self):
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
        log.info("Gemini Live session closed")

    async def feed_audio(self, pcm_chunk: bytes):
        """Feed 16kHz slin16 PCM to Gemini Live."""
        if not self._session or not self._running:
            return
        try:
            from google.genai import types
            await self._session.send(
                input=types.LiveClientRealtimeInput(
                    media_chunks=[
                        types.Blob(
                            data=pcm_chunk,
                            mime_type="audio/pcm;rate=16000",
                        )
                    ]
                )
            )
        except Exception as e:
            log.error("Gemini feed_audio error: %s", e)

    async def audio_responses(self) -> AsyncIterator[bytes]:
        """Yield 16kHz PCM audio from Gemini's responses."""
        while self._running:
            try:
                pcm = await asyncio.wait_for(
                    self._response_queue.get(), timeout=0.1)
                yield pcm
            except asyncio.TimeoutError:
                continue

    async def _receive_loop(self):
        """Background task: read Gemini Live responses and queue audio."""
        try:
            async for response in self._session.receive():
                if not self._running:
                    break

                # Extract audio data from response
                server_content = getattr(response, "server_content", None)
                if server_content and server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.inline_data and part.inline_data.data:
                            audio_24k = part.inline_data.data
                            # Downsample 24kHz → 16kHz
                            audio_16k = self._downsample_24k_to_16k(audio_24k)
                            await self._response_queue.put(audio_16k)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("Gemini receive error: %s", e)

    @staticmethod
    def _downsample_24k_to_16k(pcm_24k: bytes) -> bytes:
        """Downsample 24kHz 16-bit PCM to 16kHz using audioop.ratecv."""
        try:
            # ratecv(fragment, width, nchannels, inrate, outrate, state)
            resampled, _ = audioop.ratecv(
                pcm_24k, 2, 1,  # 2 bytes/sample, mono
                GEMINI_OUTPUT_RATE, TARGET_RATE,
                None,  # no prior state
            )
            return resampled
        except Exception:
            # Fallback: simple decimation (drop every 3rd sample from 24k → 16k ≈ 2:3 ratio)
            # This is lossy but works as fallback
            samples = struct.unpack(f"<{len(pcm_24k)//2}h", pcm_24k)
            # 24000/16000 = 3/2, so take 2 samples out of every 3
            decimated = []
            for i in range(0, len(samples) - 2, 3):
                decimated.append(samples[i])
                decimated.append(samples[i + 1])
            return struct.pack(f"<{len(decimated)}h", *decimated)
