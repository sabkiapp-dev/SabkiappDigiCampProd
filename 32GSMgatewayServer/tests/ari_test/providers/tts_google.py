"""
Google Cloud TTS Provider — Text-to-speech via Google Cloud Text-to-Speech API.

Outputs LINEAR16 PCM at 16kHz — direct match for slin16 ExternalMedia.
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseTTS

log = logging.getLogger(__name__)


class GoogleTTS(BaseTTS):

    def __init__(self, config: dict):
        self.language = config.get("language", "hi-IN")
        self.voice_name = config.get("voice_name", "hi-IN-Standard-B")
        self.speaking_rate = config.get("speaking_rate", 1.0)
        self._client = None

    async def start(self):
        try:
            from google.cloud import texttospeech_v1 as tts
        except ImportError:
            raise ImportError("Install: pip install google-cloud-texttospeech")

        self._client = tts.TextToSpeechAsyncClient()
        log.info("Google TTS started (voice=%s, lang=%s)", self.voice_name, self.language)

    async def stop(self):
        log.info("Google TTS stopped")

    async def synthesize_stream(self, text_chunks: AsyncIterator[str]) -> AsyncIterator[bytes]:
        """Accumulate text into sentences, synthesize each."""
        from google.cloud import texttospeech_v1 as tts

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
        from google.cloud import texttospeech_v1 as tts

        try:
            request = tts.SynthesizeSpeechRequest(
                input=tts.SynthesisInput(text=text),
                voice=tts.VoiceSelectionParams(
                    language_code=self.language,
                    name=self.voice_name,
                ),
                audio_config=tts.AudioConfig(
                    audio_encoding=tts.AudioEncoding.LINEAR16,
                    sample_rate_hertz=16000,
                    speaking_rate=self.speaking_rate,
                ),
            )
            response = await self._client.synthesize_speech(request=request)
            # LINEAR16 response has a 44-byte WAV header — strip it
            audio = response.audio_content
            if audio[:4] == b"RIFF":
                audio = audio[44:]  # Strip WAV header
            return audio
        except Exception as e:
            log.error("Google TTS error: %s", e)
            return None
