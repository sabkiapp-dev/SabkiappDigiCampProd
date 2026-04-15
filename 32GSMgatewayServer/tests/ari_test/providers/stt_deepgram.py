"""
Deepgram STT Provider — Real-time speech-to-text via Deepgram WebSocket API.

Accepts slin16 PCM (16kHz, 16-bit LE mono) directly — native format match.
Uses Deepgram's streaming API for low-latency partial + final transcriptions.
"""

import asyncio
import json
import logging
from typing import AsyncIterator

from providers.base import BaseSTT

log = logging.getLogger(__name__)


class DeepgramSTT(BaseSTT):

    def __init__(self, config: dict):
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "nova-2")
        self.language = config.get("language", "hi")
        self._connection = None
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False

    async def start(self):
        try:
            from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
        except ImportError:
            raise ImportError("Install deepgram-sdk: pip install deepgram-sdk")

        client = DeepgramClient(self.api_key)
        self._connection = client.listen.asyncwebsocket.v("1")

        async def on_transcript(_, result, **kwargs):
            transcript = result.channel.alternatives[0].transcript
            if transcript.strip():
                is_final = result.is_final
                if is_final:
                    await self._transcript_queue.put(transcript)
                    log.info("STT final: %s", transcript)

        self._connection.on(LiveTranscriptionEvents.Transcript, on_transcript)

        options = LiveOptions(
            model=self.model,
            language=self.language,
            encoding="linear16",
            sample_rate=16000,
            channels=1,
            interim_results=True,
            punctuate=True,
            endpointing=300,  # 300ms silence = end of utterance
        )

        await self._connection.start(options)
        self._running = True
        log.info("Deepgram STT started (model=%s, lang=%s)", self.model, self.language)

    async def stop(self):
        self._running = False
        if self._connection:
            await self._connection.finish()
        log.info("Deepgram STT stopped")

    async def feed_audio(self, pcm_chunk: bytes):
        if self._connection and self._running:
            await self._connection.send(pcm_chunk)

    async def transcriptions(self) -> AsyncIterator[str]:
        while self._running:
            try:
                text = await asyncio.wait_for(
                    self._transcript_queue.get(), timeout=0.1)
                yield text
            except asyncio.TimeoutError:
                continue
