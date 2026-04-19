"""
Whisper STT Provider — Local speech-to-text via faster-whisper.

Runs entirely on-device (no API calls). Good for privacy or offline use.
Note: RPi 4/5 can run tiny/base models. Larger models need more RAM/CPU.

Accepts slin16 PCM (16kHz, 16-bit LE mono). VAD is upstream (Silero v5 on RPi);
this provider only receives already-bracketed speech utterances.
"""

import asyncio
import logging
from typing import AsyncIterator

from providers.base import BaseSTT

log = logging.getLogger(__name__)


class WhisperSTT(BaseSTT):

    def __init__(self, config: dict):
        self.model_size = config.get("model", "base")
        self.language = config.get("language", "hi")
        self._model = None
        self._audio_buffer = bytearray()
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False

    async def start(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError("Install: pip install faster-whisper")

        self._model = WhisperModel(
            self.model_size,
            device="cpu",
            compute_type="int8",
        )
        self._running = True
        log.info("Whisper STT started (model=%s, lang=%s)", self.model_size, self.language)

    async def stop(self):
        self._running = False
        log.info("Whisper STT stopped")

    async def feed_audio(self, pcm_chunk: bytes):
        """Append pcm to the current utterance buffer. Caller triggers transcribe on utterance end."""
        if not self._running:
            return
        self._audio_buffer.extend(pcm_chunk)

    async def end_of_utterance(self):
        """Called when the upstream VAD reports speech_end. Transcribes and clears buffer."""
        if not self._running:
            return
        if not self._audio_buffer:
            return
        audio_data = bytes(self._audio_buffer)
        self._audio_buffer.clear()
        asyncio.get_event_loop().run_in_executor(None, self._transcribe, audio_data)

    def _transcribe(self, pcm_data: bytes):
        """Transcribe PCM audio using faster-whisper (blocking)."""
        import numpy as np

        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=1,
            vad_filter=False,
        )

        text = " ".join(seg.text for seg in segments).strip()
        if text:
            log.info("Whisper STT: %s", text)
            try:
                self._transcript_queue.put_nowait(text)
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
