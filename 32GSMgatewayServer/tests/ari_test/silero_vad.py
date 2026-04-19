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
