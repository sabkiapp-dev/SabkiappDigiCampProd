"""Silero VAD v5 — runs on RPi. Gates ulaw audio so only speech crosses WS."""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "silero"
MODEL_URL = "https://huggingface.co/runanywhere/silero-vad-v5/resolve/main/silero_vad.onnx"
MODEL_FILENAME = "silero_vad_v5.onnx"


def model_path() -> str:
    """Return path to Silero v5 ONNX. Downloads once if not cached."""
    env = os.environ.get("SILERO_MODEL_PATH")
    if env:
        return env
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / MODEL_FILENAME
    if not target.exists():
        tmp = target.with_suffix(".onnx.part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.rename(target)
    return str(target)


import threading
import numpy as np

_session_lock = threading.Lock()
_session = None  # onnxruntime.InferenceSession, shared across streams


def _get_session():
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                import onnxruntime as ort
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 1
                opts.inter_op_num_threads = 1
                _session = ort.InferenceSession(
                    model_path(),
                    sess_options=opts,
                    providers=["CPUExecutionProvider"],
                )
    return _session


SAMPLE_RATE = 16000
FRAME_SIZE = 512     # Silero v5 expects 512 new samples per frame @ 16kHz (32ms)
CONTEXT_SIZE = 64    # prepended to each frame — last 64 samples of the prior frame


class SileroStream:
    """Per-call Silero VAD v5 stream. Holds LSTM state + 64-sample context between frames."""

    def __init__(self):
        self._session = _get_session()
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT_SIZE, dtype=np.float32)

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT_SIZE, dtype=np.float32)

    def process(self, frame_float32: np.ndarray) -> float:
        """Run one 512-sample frame through the model. Returns speech probability.

        The model input is 64 context samples (from the previous frame) + 512 new samples.
        Context is maintained automatically — caller passes only the 512 new samples.
        """
        if frame_float32.shape != (FRAME_SIZE,):
            raise ValueError(f"frame must be shape ({FRAME_SIZE},), got {frame_float32.shape}")
        if frame_float32.dtype != np.float32:
            frame_float32 = frame_float32.astype(np.float32)
        # Prepend context: [ctx(64), frame(512)] = 576 samples total
        x_with_ctx = np.concatenate([self._context, frame_float32])  # (576,)
        x = x_with_ctx.reshape(1, CONTEXT_SIZE + FRAME_SIZE)
        prob, new_state = self._session.run(
            None,
            {"input": x, "sr": self._sr, "state": self._state},
        )
        self._state = new_state
        self._context = x_with_ctx[-CONTEXT_SIZE:].copy()  # last 64 samples → next call
        return float(prob[0, 0])


import audioop


class UlawTo16kFrames:
    """Accepts ulaw @ 8 kHz (arbitrary chunk sizes), yields float32 frames of 512 samples @ 16 kHz."""

    def __init__(self):
        self._resample_state = None  # audioop.ratecv state
        self._pcm16_buf = bytearray()

    def reset(self):
        self._resample_state = None
        self._pcm16_buf.clear()

    def feed(self, ulaw_chunk: bytes):
        """Feed any amount of ulaw bytes. Yields 0+ np.float32 arrays of shape (512,)."""
        pcm8k = audioop.ulaw2lin(ulaw_chunk, 2)
        pcm16k, self._resample_state = audioop.ratecv(
            pcm8k, 2, 1, 8000, 16000, self._resample_state
        )
        self._pcm16_buf.extend(pcm16k)

        bytes_per_frame = FRAME_SIZE * 2  # 512 samples × int16 = 1024 bytes
        while len(self._pcm16_buf) >= bytes_per_frame:
            raw = bytes(self._pcm16_buf[:bytes_per_frame])
            del self._pcm16_buf[:bytes_per_frame]
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            yield samples


from typing import Callable

SPEECH_THRESHOLD = 0.5
ONSET_FRAMES = 2       # ~64 ms of speech to trigger speech_start
OFFSET_FRAMES = 25     # ~800 ms of silence to trigger speech_end
MIN_UTTERANCE_FRAMES = 3  # ~96 ms — discard blips

STATE_IDLE = "idle"
STATE_SPEAKING = "speaking"


class VADGate:
    """Full pipeline: ulaw bytes → resample → silero → state machine → callbacks.

    Callbacks:
      on_speech_start():             called once at utterance onset
      on_speech_audio(ulaw: bytes):  called for each ulaw chunk while SPEAKING
      on_speech_end():               called once at utterance offset
    """

    def __init__(
        self,
        on_speech_start: Callable[[], None],
        on_speech_audio: Callable[[bytes], None],
        on_speech_end: Callable[[], None],
    ):
        self._on_start = on_speech_start
        self._on_audio = on_speech_audio
        self._on_end = on_speech_end
        self._stream = SileroStream()
        self._frames = UlawTo16kFrames()
        self._state = STATE_IDLE
        self._consec_speech = 0
        self._consec_silence = 0
        self._speech_frame_count = 0
        # Pending ulaw buffered during ONSET_FRAMES window — flushed on speech_start
        self._pending_ulaw = bytearray()

    def reset(self):
        """Call at the start of a new call. Resets VAD state + LSTM."""
        self._stream.reset()
        self._frames.reset()
        self._state = STATE_IDLE
        self._consec_speech = 0
        self._consec_silence = 0
        self._speech_frame_count = 0
        self._pending_ulaw.clear()

    def is_speaking(self) -> bool:
        return self._state == STATE_SPEAKING

    def feed(self, ulaw_chunk: bytes):
        """Feed raw ulaw bytes from RTP. Drives the VAD pipeline and callbacks."""
        for frame in self._frames.feed(ulaw_chunk):
            self._on_frame(frame, ulaw_chunk)

    def _on_frame(self, frame, ulaw_chunk: bytes):
        prob = self._stream.process(frame)
        is_speech = prob >= SPEECH_THRESHOLD

        if self._state == STATE_IDLE:
            # Keep a small rolling buffer so the first audio after speech_start isn't lost
            self._pending_ulaw.extend(ulaw_chunk)
            # Cap pending buffer at ~200 ms ulaw (8 kHz × 0.2 s = 1600 bytes)
            if len(self._pending_ulaw) > 1600:
                del self._pending_ulaw[:-1600]

            if is_speech:
                self._consec_speech += 1
                if self._consec_speech >= ONSET_FRAMES:
                    self._state = STATE_SPEAKING
                    self._speech_frame_count = self._consec_speech
                    self._consec_silence = 0
                    self._on_start()
                    if self._pending_ulaw:
                        self._on_audio(bytes(self._pending_ulaw))
                        self._pending_ulaw.clear()
            else:
                self._consec_speech = 0
        else:  # STATE_SPEAKING
            self._on_audio(ulaw_chunk)
            self._speech_frame_count += 1
            if is_speech:
                self._consec_silence = 0
            else:
                self._consec_silence += 1
                if self._consec_silence >= OFFSET_FRAMES:
                    emitted_end = self._speech_frame_count >= MIN_UTTERANCE_FRAMES
                    self._state = STATE_IDLE
                    self._consec_speech = 0
                    self._consec_silence = 0
                    self._speech_frame_count = 0
                    self._pending_ulaw.clear()
                    if emitted_end:
                        self._on_end()
