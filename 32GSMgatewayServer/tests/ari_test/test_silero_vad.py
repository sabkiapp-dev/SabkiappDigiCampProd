"""Unit tests for silero_vad module."""
from pathlib import Path

import numpy as np
import pytest

import silero_vad


def test_model_path_uses_env_override(tmp_path, monkeypatch):
    fake = tmp_path / "override.onnx"
    fake.write_bytes(b"\x00\x01\x02")  # non-empty
    monkeypatch.setenv("SILERO_MODEL_PATH", str(fake))
    assert silero_vad.model_path() == str(fake)


def test_model_path_downloads_to_cache_if_missing(tmp_path, monkeypatch):
    cache_root = tmp_path / "cache"
    monkeypatch.delenv("SILERO_MODEL_PATH", raising=False)
    monkeypatch.setattr(silero_vad, "CACHE_DIR", cache_root)
    # First call downloads
    p = silero_vad.model_path()
    assert Path(p).exists()
    assert Path(p).stat().st_size > 100_000  # ONNX is ~2.2MB

    # Second call is idempotent (no re-download)
    mtime = Path(p).stat().st_mtime
    p2 = silero_vad.model_path()
    assert p2 == p
    assert Path(p).stat().st_mtime == mtime


def test_silero_stream_silence_has_low_prob():
    stream = silero_vad.SileroStream()
    silence = np.zeros(512, dtype=np.float32)
    prob = stream.process(silence)
    assert 0.0 <= prob <= 1.0
    assert prob < 0.2, f"silence should have low prob, got {prob}"


def test_silero_stream_tone_has_valid_prob():
    """A 440Hz tone is not speech — prob stays in valid range regardless."""
    stream = silero_vad.SileroStream()
    t = np.arange(512, dtype=np.float32) / 16000.0
    tone = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    prob = stream.process(tone)
    assert 0.0 <= prob <= 1.0


def test_silero_stream_reset_clears_state():
    stream = silero_vad.SileroStream()
    frame = np.random.randn(512).astype(np.float32) * 0.1
    stream.process(frame)
    stream.reset()
    assert float(np.abs(stream._state).sum()) == 0.0
