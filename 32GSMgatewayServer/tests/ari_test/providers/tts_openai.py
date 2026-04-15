"""
OpenAI TTS Provider — Text-to-speech via OpenAI Audio API.

OpenAI TTS outputs various formats. We request PCM and resample to 16kHz.
"""

import asyncio
import audioop
import logging
from typing import AsyncIterator

from providers.base import BaseTTS

log = logging.getLogger(__name__)


class OpenAITTS(BaseTTS):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "tts-1")
        self.voice = config.get("voice", "alloy")
        self._client = None

    async def start(self):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("Install: pip install openai")

        self._client = AsyncOpenAI(api_key=self.api_key)
        log.info("OpenAI TTS started (model=%s, voice=%s)", self.model, self.voice)

    async def stop(self):
        log.info("OpenAI TTS stopped")

    async def synthesize_stream(self, text_chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
        sentence_buffer = ""

        async for chunk in text_chunks:
            sentence_buffer += chunk

            while any(p in sentence_buffer for p in [".", "!", "?", "।"]):
                for i, ch in enumerate(sentence_buffer):
                    if ch in ".!?।":
                        sentence = sentence_buffer[:i + 1].strip()
                        sentence_buffer = sentence_buffer[i + 1:]
                        if sentence:
                            pcm = await self._synthesize_one(sentence)
                            if pcm:
                                yield pcm
                        break

        if sentence_buffer.strip():
            pcm = await self._synthesize_one(sentence_buffer.strip())
            if pcm:
                yield pcm

    async def _synthesize_one(self, text: str) -> bytes | None:
        try:
            response = await self._client.audio.speech.create(
                model=self.model,
                voice=self.voice,
                input=text,
                response_format="pcm",  # Raw PCM, 24kHz, 16-bit mono
            )

            # OpenAI TTS PCM is 24kHz — downsample to 16kHz
            pcm_24k = response.content
            pcm_16k, _ = audioop.ratecv(pcm_24k, 2, 1, 24000, 16000, None)
            return pcm_16k

        except Exception as e:
            log.error("OpenAI TTS error: %s", e)
            return None
