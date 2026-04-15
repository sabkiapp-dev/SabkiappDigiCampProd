"""
ElevenLabs TTS Provider — Streaming text-to-speech via ElevenLabs API.

Outputs audio in slin16 format (16kHz, 16-bit LE PCM).
ElevenLabs streams MP3/PCM — we request PCM and resample if needed.
"""

import asyncio
import audioop
import io
import logging
from typing import AsyncIterator

from providers.base import BaseTTS

log = logging.getLogger(__name__)

TARGET_RATE = 16000


class ElevenLabsTTS(BaseTTS):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.voice_id = config.get("voice_id", "RABOvaPec1ymXz02oDQi")
        self.model = config.get("model", "eleven_multilingual_v2")
        self._client = None

    async def start(self):
        try:
            from elevenlabs.client import AsyncElevenLabs
        except ImportError:
            raise ImportError("Install: pip install elevenlabs")

        self._client = AsyncElevenLabs(api_key=self.api_key)
        log.info("ElevenLabs TTS started (voice=%s, model=%s)", self.voice_id, self.model)

    async def stop(self):
        log.info("ElevenLabs TTS stopped")

    async def synthesize_stream(self, text_chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Accumulate text chunks into sentences, synthesize each."""
        sentence_buffer = ""

        async for chunk in text_chunks:
            sentence_buffer += chunk

            # Synthesize when we have a complete sentence
            while any(p in sentence_buffer for p in [".", "!", "?", "।"]):
                for i, ch in enumerate(sentence_buffer):
                    if ch in ".!?।":
                        sentence = sentence_buffer[:i + 1].strip()
                        sentence_buffer = sentence_buffer[i + 1:]
                        if sentence:
                            async for pcm in self._synthesize_sentence(sentence):
                                yield pcm
                        break

        # Handle remaining text
        if sentence_buffer.strip():
            async for pcm in self._synthesize_sentence(sentence_buffer.strip()):
                yield pcm

    async def _synthesize_sentence(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize a single sentence and yield PCM chunks."""
        try:
            # Request raw PCM from ElevenLabs
            audio_generator = self._client.text_to_speech.convert(
                voice_id=self.voice_id,
                text=text,
                model_id=self.model,
                output_format="pcm_16000",  # 16kHz 16-bit PCM
            )

            async for chunk in audio_generator:
                if chunk:
                    yield chunk

        except Exception as e:
            log.error("ElevenLabs TTS error: %s", e)
