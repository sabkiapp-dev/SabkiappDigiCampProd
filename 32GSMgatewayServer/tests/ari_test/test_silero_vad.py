"""Unit tests for silero_vad module."""
from pathlib import Path

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
