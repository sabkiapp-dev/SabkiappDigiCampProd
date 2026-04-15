"""
Google Cloud STT Provider — Real-time speech-to-text via Google Cloud Speech API.

Uses streaming recognition for low-latency transcription.
Accepts slin16 PCM (16kHz, 16-bit LE mono).
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseSTT

log = logging.getLogger(__name__)


class GoogleSTT(BaseSTT):

    def __init__(self, config: dict):
        self.language = config.get("language", "hi-IN")
        self.model = config.get("model", "default")
        self._client = None
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self._stream_task = None

    async def start(self):
        try:
            from google.cloud import speech
        except ImportError:
            raise ImportError("Install: pip install google-cloud-speech")

        self._client = speech.SpeechAsyncClient()
        self._running = True
        self._stream_task = asyncio.create_task(self._stream_loop())
        log.info("Google STT started (lang=%s)", self.language)

    async def stop(self):
        self._running = False
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        log.info("Google STT stopped")

    async def feed_audio(self, pcm_chunk: bytes):
        if self._running:
            try:
                self._audio_queue.put_nowait(pcm_chunk)
            except asyncio.QueueFull:
                pass

    async def transcriptions(self) -> AsyncIterator[str]:
        while self._running:
            try:
                text = await asyncio.wait_for(
                    self._transcript_queue.get(), timeout=0.1)
                yield text
            except asyncio.TimeoutError:
                continue

    async def _stream_loop(self):
        """Continuously run streaming recognition sessions."""
        from google.cloud import speech

        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=self.language,
            enable_automatic_punctuation=True,
        )
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )

        while self._running:
            try:
                requests_gen = self._audio_generator(streaming_config)
                responses = await self._client.streaming_recognize(requests=requests_gen)

                async for response in responses:
                    for result in response.results:
                        if result.is_final:
                            transcript = result.alternatives[0].transcript
                            if transcript.strip():
                                await self._transcript_queue.put(transcript)
                                log.info("STT final: %s", transcript)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("Google STT stream error: %s", e)
                await asyncio.sleep(1)

    async def _audio_generator(self, streaming_config):
        """Yield streaming recognition requests."""
        from google.cloud import speech

        yield speech.StreamingRecognizeRequest(streaming_config=streaming_config)

        while self._running:
            try:
                chunk = await asyncio.wait_for(
                    self._audio_queue.get(), timeout=0.5)
                yield speech.StreamingRecognizeRequest(audio_content=chunk)
            except asyncio.TimeoutError:
                continue
