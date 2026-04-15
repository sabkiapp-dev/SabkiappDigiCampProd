"""
Whisper STT Provider — Local speech-to-text via faster-whisper.

Runs entirely on-device (no API calls). Good for privacy or offline use.
Note: RPi 4/5 can run tiny/base models. Larger models need more RAM/CPU.

Accepts slin16 PCM (16kHz, 16-bit LE mono).
Buffers audio and transcribes on voice activity detection (silence-based).
"""

import asyncio
import logging
import struct
from typing import AsyncIterator

from providers.base import BaseSTT

log = logging.getLogger(__name__)

# Silence threshold (16-bit samples, adjust for your mic/environment)
SILENCE_THRESHOLD = 500
SILENCE_DURATION_MS = 800  # ms of silence before transcribing
FRAMES_PER_MS = 16  # 16kHz = 16 samples per ms


class WhisperSTT(BaseSTT):

    def __init__(self, config: dict):
        self.model_size = config.get("model", "base")
        self.language = config.get("language", "hi")
        self._model = None
        self._audio_buffer = bytearray()
        self._silence_frames = 0
        self._has_speech = False
        self._transcript_queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False

    async def start(self):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError("Install: pip install faster-whisper")

        # Use CPU for RPi; int8 quantization for speed
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
        if not self._running:
            return

        # Check for silence/speech
        samples = struct.unpack(f"<{len(pcm_chunk)//2}h", pcm_chunk)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5

        if rms > SILENCE_THRESHOLD:
            self._has_speech = True
            self._silence_frames = 0
            self._audio_buffer.extend(pcm_chunk)
        elif self._has_speech:
            self._silence_frames += len(samples)
            self._audio_buffer.extend(pcm_chunk)

            if self._silence_frames >= SILENCE_DURATION_MS * FRAMES_PER_MS:
                # End of utterance — transcribe
                audio_data = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                self._has_speech = False
                self._silence_frames = 0

                # Run transcription in thread (CPU-bound)
                asyncio.get_event_loop().run_in_executor(
                    None, self._transcribe, audio_data)

    def _transcribe(self, pcm_data: bytes):
        """Transcribe PCM audio using faster-whisper (blocking)."""
        import numpy as np

        # Convert PCM bytes to float32 array (-1.0 to 1.0)
        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=1,  # Fastest
            vad_filter=True,
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
