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
FRAME_SIZE = 512  # Silero v5 expects 512 samples @ 16kHz (32ms)


class SileroStream:
    """Per-call Silero VAD v5 stream. Holds LSTM state between frames."""

    def __init__(self):
        self._session = _get_session()
        self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def reset(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def process(self, frame_float32: np.ndarray) -> float:
        """Run one 512-sample frame through the model. Returns speech probability."""
        if frame_float32.shape != (FRAME_SIZE,):
            raise ValueError(f"frame must be shape ({FRAME_SIZE},), got {frame_float32.shape}")
        if frame_float32.dtype != np.float32:
            frame_float32 = frame_float32.astype(np.float32)
        x = frame_float32.reshape(1, FRAME_SIZE)
        prob, new_state = self._session.run(
            None,
            {"input": x, "sr": self._sr, "state": self._state},
        )
        self._state = new_state
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
