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


def test_ulaw_to_16k_frames_yields_correct_sizes():
    """Feed 10 packets of 160-byte ulaw (20 ms each @ 8 kHz).
       Should yield frames of 512 PCM samples @ 16 kHz."""
    acc = silero_vad.UlawTo16kFrames()
    ulaw_silence = b"\x7f" * 160  # 20 ms of ulaw silence
    frames = []
    for _ in range(10):
        for f in acc.feed(ulaw_silence):
            frames.append(f)

    # 10 packets × 20 ms = 200 ms of audio. 200 ms @ 16 kHz = 3200 samples.
    # 3200 / 512 = 6 full frames (rest buffered).
    assert len(frames) == 6
    for f in frames:
        assert f.shape == (512,)
        assert f.dtype == np.float32
        assert np.abs(f).max() < 0.01  # silence


def test_vad_gate_emits_start_audio_end(monkeypatch):
    """Feed synthetic probabilities via _on_frame directly; assert callback sequence."""
    events = []

    def mock_process(self, frame):
        return float(frame[0])  # first sample == desired prob (hack for test)

    monkeypatch.setattr(silero_vad.SileroStream, "process", mock_process)

    gate = silero_vad.VADGate(
        on_speech_start=lambda: events.append(("start",)),
        on_speech_audio=lambda b: events.append(("audio", len(b))),
        on_speech_end=lambda: events.append(("end",)),
    )

    def push_prob(p, ulaw_bytes=b"\x7f" * 320):
        frame = np.zeros(512, dtype=np.float32)
        frame[0] = p
        gate._on_frame(frame, ulaw_bytes)

    # 2 silence frames → no events
    push_prob(0.0)
    push_prob(0.0)
    assert events == []

    # 2 speech frames → triggers start (ONSET_FRAMES=2)
    push_prob(0.9)
    push_prob(0.9)
    assert ("start",) in events
    assert any(e[0] == "audio" for e in events)
    assert gate.is_speaking()

    # 25 silence frames → triggers end (OFFSET_FRAMES=25)
    for _ in range(25):
        push_prob(0.1)
    assert ("end",) in events
    assert not gate.is_speaking()
