# Silero VAD v5 on RPi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom RMS VAD on the PC and the faster-whisper internal VAD pass with a single Silero VAD v5 gate running on the RPi. All STT providers on the PC receive only speech — no local VAD on the PC side.

**Architecture:** RPi runs the Silero v5 ONNX model on 32 ms frames after resampling ulaw → PCM16 @ 16 kHz. A state machine emits `speech_start` / `speech_end` JSON markers over the existing WebSocket and gates the forwarding of ulaw binary frames so only speech crosses the network. The PC's `_STTBase` loses its VAD and simply buffers audio between markers.

**Tech Stack:** Python 3.9+, `onnxruntime` (CPU ARM on RPi), `numpy`, `audioop` (ulaw↔PCM + resample), `websocket-client` (Pi side), `websockets` (PC side, already in use), `faster-whisper` (flag change only).

**Reference spec:** `docs/superpowers/specs/2026-04-19-silero-vad-v5-rpi-design.md`

---

## File Structure

| File | Change | Purpose |
|---|---|---|
| `32GSMgatewayServer/tests/ari_test/silero_vad.py` | **Create** | Model loader + `SileroStream` (inference) + `UlawTo16kFrames` (resampler/accumulator) + `VADGate` (state machine) |
| `32GSMgatewayServer/tests/ari_test/test_silero_vad.py` | **Create** | Unit tests for the module above |
| `32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py` | **Modify** | Wire `VADGate` into the RTP → WS path; reset stream on `call_start` |
| `32GSMgatewayServer/tests/ari_test/ai_server.py` | **Modify** | Strip RMS VAD from `_STTBase`; handle `speech_start` / `speech_end`; flip `vad_filter=False` |
| `32GSMgatewayServer/tests/ari_test/providers/stt_whisper.py` | **Modify** | Remove RMS gate; flip `vad_filter=False`; keep only `_transcribe()` from buffered audio |
| `32GSMgatewayServer/tests/ari_test/requirements_test.txt` | **Modify** | Add `onnxruntime`, un-comment `faster-whisper` dep optionally (no other change) |

---

## Task 1: Add dependencies

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/requirements_test.txt`

- [ ] **Step 1: Add `onnxruntime` to requirements**

Replace the file contents with:

```
# Core — ARI + RTP
requests>=2.28
websocket-client>=1.5
pyyaml>=6.0

# VAD — Silero v5 (runs on RPi)
onnxruntime>=1.17
numpy>=1.24

# STT providers
deepgram-sdk>=3.0
google-cloud-speech>=2.16
# faster-whisper>=1.0  # optional — skip on RPi if low RAM

# LLM providers
google-genai>=1.0
openai>=1.0

# TTS providers
elevenlabs>=1.0
google-cloud-texttospeech>=2.16
```

- [ ] **Step 2: Install locally for test runs**

Run (from repo root):

```bash
pip install "onnxruntime>=1.17" "numpy>=1.24"
```

Expected: successful install, both packages importable.

- [ ] **Step 3: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/requirements_test.txt
git commit -m "build(vad): add onnxruntime + numpy for Silero VAD v5"
```

---

## Task 2: Model loader — download + cache

**Files:**
- Create: `32GSMgatewayServer/tests/ari_test/silero_vad.py`
- Create: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing test**

Create `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`:

```python
"""Unit tests for silero_vad module."""
import os
import tempfile
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
```

- [ ] **Step 2: Run test to verify it fails**

Run from `32GSMgatewayServer/tests/ari_test/`:

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: FAIL with `ModuleNotFoundError: silero_vad` (module not yet created).

- [ ] **Step 3: Write minimal implementation**

Create `32GSMgatewayServer/tests/ari_test/silero_vad.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run (first call downloads ~2.2 MB from HF):

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: 2 passing tests.

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/silero_vad.py 32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "feat(vad): add Silero v5 model loader with HF download + env override"
```

---

## Task 3: SileroStream — inference wrapper

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/silero_vad.py`
- Modify: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing test**

Append to `test_silero_vad.py`:

```python
import numpy as np
import struct


def test_silero_stream_silence_has_low_prob():
    stream = silero_vad.SileroStream()
    silence = np.zeros(512, dtype=np.float32)
    prob = stream.process(silence)
    assert 0.0 <= prob <= 1.0
    assert prob < 0.2, f"silence should have low prob, got {prob}"


def test_silero_stream_tone_has_varied_prob():
    """A 440Hz tone is not speech — prob should stay low. But it must run without error."""
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
    # After reset, state tensor should be zeroed
    assert float(np.abs(stream._state).sum()) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: FAIL with `AttributeError: module ... has no attribute 'SileroStream'`.

- [ ] **Step 3: Implement SileroStream**

Append to `silero_vad.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: 5 passing tests (2 from Task 2 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/silero_vad.py 32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "feat(vad): add SileroStream inference wrapper with LSTM state"
```

---

## Task 4: UlawTo16kFrames — resampler + frame accumulator

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/silero_vad.py`
- Modify: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing test**

Append to `test_silero_vad.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: FAIL with `AttributeError: ... 'UlawTo16kFrames'`.

- [ ] **Step 3: Implement UlawTo16kFrames**

Append to `silero_vad.py`:

```python
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
```

- [ ] **Step 4: Run tests**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: 6 passing tests.

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/silero_vad.py 32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "feat(vad): add UlawTo16kFrames resampler/accumulator"
```

---

## Task 5: VADGate — state machine

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/silero_vad.py`
- Modify: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing test**

Append to `test_silero_vad.py`:

```python
def test_vad_gate_emits_start_and_end(monkeypatch):
    """Feed a pattern: silence → speech → silence. Expect speech_start, audio, speech_end."""
    events = []

    def mock_process(self, frame):
        # Alternate based on a marker stored in the frame
        return float(frame[0])  # first sample == desired prob (hack for test)

    monkeypatch.setattr(silero_vad.SileroStream, "process", mock_process)

    gate = silero_vad.VADGate(
        on_speech_start=lambda: events.append(("start",)),
        on_speech_audio=lambda b: events.append(("audio", len(b))),
        on_speech_end=lambda: events.append(("end",)),
    )
    # Helper: craft ulaw that, after ulaw2lin+ratecv, sets the first sample to `prob`
    # Simpler: bypass the pipeline and inject frames directly
    def push_prob(p, ulaw_bytes=b"\x7f" * 320):
        # For the state machine test, stub out the frame extractor to yield a frame with first sample = p
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

    # 25 silence frames → triggers end (OFFSET_FRAMES=25)
    for _ in range(25):
        push_prob(0.1)
    assert ("end",) in events
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: FAIL with `AttributeError: ... 'VADGate'`.

- [ ] **Step 3: Implement VADGate**

Append to `silero_vad.py`:

```python
from typing import Callable, Optional

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
```

Note: the test calls `gate._on_frame(frame, ulaw_bytes)` directly, bypassing `feed()`. That's by design — it lets the unit test drive the state machine with synthetic probabilities without going through Silero inference.

- [ ] **Step 4: Run tests**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: 7 passing tests.

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/silero_vad.py 32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "feat(vad): add VADGate state machine with onset/offset hysteresis"
```

---

## Task 6: Wire VADGate into rpi_audio_bridge.py

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py`

- [ ] **Step 1: Replace forward_audio with VAD-gated version**

In `rpi_audio_bridge.py`, at the top of the file (after line 23 imports) add:

```python
import silero_vad
```

Find the block at lines 355–364 that reads:

```python
    # RTP → AI server forwarding
    def forward_audio(ulaw_payload):
        if ai_ws and ai_connected.is_set():
            try:
                ai_ws.send(ulaw_payload, opcode=0x2)  # binary
            except Exception:
                pass

    rtp.on_audio = forward_audio
    rtp.start()
```

Replace with:

```python
    # VAD gate on RPi — only speech-bracketed audio goes to PC
    def _send_json(obj):
        if ai_ws and ai_connected.is_set():
            try:
                ai_ws.send(json.dumps(obj))
            except Exception:
                pass

    def _send_ulaw(ulaw: bytes):
        if ai_ws and ai_connected.is_set():
            try:
                ai_ws.send(ulaw, opcode=0x2)  # binary
            except Exception:
                pass

    vad = silero_vad.VADGate(
        on_speech_start=lambda: _send_json({"type": "speech_start"}),
        on_speech_audio=_send_ulaw,
        on_speech_end=lambda: _send_json({"type": "speech_end"}),
    )

    def forward_audio(ulaw_payload):
        vad.feed(ulaw_payload)

    rtp.on_audio = forward_audio
    rtp.start()
```

- [ ] **Step 2: Reset VAD on call_start; flush mid-utterance on call_end**

Find the `on_call_start` and `on_call_end` callbacks (lines 367–384). Replace with:

```python
    # ARI callbacks
    def on_call_start(is_incoming, caller):
        vad.reset()
        if ai_ws:
            ai_ws.send(json.dumps({
                "type": "call_start",
                "endpoint": args.endpoint or "incoming",
                "mode": "incoming" if is_incoming else "outbound",
                "caller": caller,
                "task_prompt": args.task_prompt or None,
            }))

    def on_call_end():
        # If we're mid-utterance, close the bracket so PC flushes its buffer
        if vad._state == silero_vad.STATE_SPEAKING:
            _send_json({"type": "speech_end"})
        vad.reset()
        rtp.flush_queue()  # discard any queued audio for ended call
        if ai_ws:
            ai_ws.send(json.dumps({"type": "call_end"}))
```

- [ ] **Step 3: Smoke-test import**

Run:

```bash
cd 32GSMgatewayServer/tests/ari_test && python -c "import rpi_audio_bridge"
```

Expected: no exception.

- [ ] **Step 4: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py
git commit -m "feat(vad): gate RTP→WS audio through Silero VADGate on RPi"
```

---

## Task 7: Strip RMS VAD from ai_server.py _STTBase

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/ai_server.py`

- [ ] **Step 1: Replace _STTBase with buffer-only version**

Find `class _STTBase:` at line 42. Replace the full class block (lines 42–76, ending at the blank line before `# ── STT: faster-whisper (local) ───…`) with:

```python
class _STTBase:
    """Shared buffer for audio bracketed by speech_start / speech_end from RPi."""

    MIN_SPEECH_BYTES = 3200  # ~100 ms of 16-bit PCM @ 16 kHz — smaller = drop

    def _init_vad(self):
        self._buffer = bytearray()

    def has_utterance(self) -> bool:
        return len(self._buffer) >= self.MIN_SPEECH_BYTES

    def take_utterance(self) -> bytes:
        data = bytes(self._buffer)
        self._buffer.clear()
        return data
```

- [ ] **Step 2: Remove `_has_speech` reference in call_start handler**

Find lines 697–698:

```python
                    stt._buffer.clear()
                    stt._has_speech = False
```

Replace with:

```python
                    stt._buffer.clear()
```

- [ ] **Step 3: Flip vad_filter=False in WhisperSTT._transcribe**

Find lines 106–112 (inside `WhisperSTT._transcribe`) that read:

```python
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )
```

Replace with:

```python
        segments, _ = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            vad_filter=False,
        )
```

- [ ] **Step 4: Smoke-test import**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -c "import ai_server"
```

Expected: no exception.

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/ai_server.py
git commit -m "refactor(stt): strip RMS VAD from _STTBase, flip vad_filter=False"
```

---

## Task 8: Replace binary / JSON handlers in handle_client

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/ai_server.py`

- [ ] **Step 1: Replace the binary-message branch**

Find lines 574–588, the binary branch of the `async for message in ws:` loop:

```python
            if isinstance(message, bytes):
                _mon_send(message)  # forward incoming ulaw to admin monitor
                pcm_8k = audioop.ulaw2lin(message, 2)
                pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)

                # Debug every ~2 seconds
                pkt_count += 1
                if pkt_count % 100 == 1:
                    samples = struct.unpack(f"<{len(pcm_16k)//2}h", pcm_16k)
                    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                    log.info(f"Audio: RMS={rms:.0f} has_speech={stt._has_speech} buf={len(stt._buffer)}")

                audio_chunk = stt.vad(pcm_16k)
                if audio_chunk:
```

Replace with (keeping the existing `if audio_chunk:` body below untouched for now — that moves in Step 2):

```python
            if isinstance(message, bytes):
                _mon_send(message)  # forward incoming ulaw to admin monitor
                if stt_resample_state is None:
                    pcm_8k = audioop.ulaw2lin(message, 2)
                    pcm_16k, stt_resample_state = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
                else:
                    pcm_8k = audioop.ulaw2lin(message, 2)
                    pcm_16k, stt_resample_state = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, stt_resample_state)
                stt._buffer.extend(pcm_16k)
                pkt_count += 1
                if pkt_count % 100 == 1:
                    log.info(f"Audio bracketed: buf={len(stt._buffer)}")
```

Also at the top of `handle_client()`, near the other `nonlocal`/state vars (around line 565–571), add:

```python
    stt_resample_state = None  # audioop.ratecv state — persists across binary msgs within an utterance
```

- [ ] **Step 2: Lift the pipeline body into a `speech_end` handler**

The existing body under `if audio_chunk:` (lines 588–688) runs an async pipeline per utterance. That whole block needs to move under the new `speech_end` dispatch.

Refactor by extracting a local helper `_start_pipeline(chunk)`. Inside `handle_client()`, just after the `stt_resample_state = None` line, insert:

```python
    async def _start_pipeline(audio_chunk: bytes):
        nonlocal processing, current_task, stop_event, is_speaking, speaking_until, user_spoke
        user_spoke = True
        now = time.monotonic()
        if is_speaking or now < speaking_until:
            return  # echo suppression
        if processing and current_task and stop_event:
            log.info("Barge-in detected — cancelling pipeline")
            stop_event.set()
            current_task.cancel()
            processing = False
        if processing or is_speaking or now < speaking_until:
            return
        processing = True
        stop_event = asyncio.Event()

        async def _pipeline(chunk=audio_chunk, se=stop_event):
            nonlocal processing, is_speaking, speaking_until
            loop = asyncio.get_event_loop()
            try:
                # STT (non-blocking)
                dur = len(chunk) / (16000 * 2)
                log.info(f"STT: transcribing {dur:.2f}s...")
                transcript = await loop.run_in_executor(None, stt._transcribe, chunk)
                if not transcript or se.is_set():
                    log.info("STT: empty or cancelled")
                    return

                # LLM streaming — sentences arrive via queue
                sentence_q = asyncio.Queue()

                def _stream():
                    try:
                        llm.stream_sentences(transcript, sentence_q, loop, se)
                    except Exception as e:
                        err = str(e)
                        if "429" in err or "quota" in err.lower():
                            asyncio.run_coroutine_threadsafe(
                                sentence_q.put("माफ करें, अभी सेवा उपलब्ध नहीं है।"), loop)
                        elif "503" in err:
                            asyncio.run_coroutine_threadsafe(
                                sentence_q.put("माफ करें, सेवा व्यस्त है।"), loop)
                        else:
                            log.error(f"LLM error: {e}")
                        asyncio.run_coroutine_threadsafe(sentence_q.put(None), loop)

                loop.run_in_executor(None, _stream)

                # TTS each sentence as it arrives — overlap LLM + TTS
                is_speaking = True
                while not se.is_set():
                    try:
                        sentence = await asyncio.wait_for(sentence_q.get(), timeout=10.0)
                    except asyncio.TimeoutError:
                        log.warning("LLM sentence timeout")
                        break
                    if sentence is None:
                        break
                    if se.is_set():
                        break

                    task_complete = "TASK_COMPLETE" in sentence
                    sentence = sentence.replace("TASK_COMPLETE", "").strip()
                    m_exec = re.search(r"EXECUTE_TASK:(\d+)", sentence)
                    execute_task_id = None
                    if m_exec:
                        execute_task_id = m_exec.group(1)
                        sentence = re.sub(r"EXECUTE_TASK:\d+", "", sentence).strip()
                        log.info(f"[AI] TASK_TRIGGER: task_id={execute_task_id}")

                    if not sentence:
                        if task_complete:
                            await ws.send(json.dumps({"type": "hangup"}))
                        break

                    pcm = await loop.run_in_executor(None, tts.synthesize, sentence)
                    if pcm and not se.is_set():
                        pcm_8k_out, _ = audioop.ratecv(pcm, 2, 1, 16000, 8000, None)
                        ulaw_out = audioop.lin2ulaw(pcm_8k_out, 2)
                        await ws.send(ulaw_out)
                        _mon_send(ulaw_out)
                        audio_secs = len(ulaw_out) / 8000
                        speaking_until = time.monotonic() + audio_secs + 0.6
                        log.info(f"Sent {len(ulaw_out)}B for: \"{sentence[:40]}\"")

                    if task_complete and not se.is_set():
                        await asyncio.sleep(audio_secs + 0.3)
                        await ws.send(json.dumps({"type": "hangup"}))
                        break

            except asyncio.CancelledError:
                pass
            except Exception as e:
                log.error(f"Pipeline error: {e}")
            finally:
                is_speaking = False
                processing = False

        current_task = asyncio.create_task(_pipeline())
```

Use the exact original `_pipeline` body — do not modify its logic. Only its triggering moves from "VAD fired" to "speech_end received".

- [ ] **Step 3: Remove the old `audio_chunk` trigger block and add speech_start / speech_end handlers**

Delete the original body under `if audio_chunk:` (the block from line 588 to line 688 inclusive — where `current_task = asyncio.create_task(_pipeline())` closes the block).

In the `elif isinstance(message, str):` branch (line 690 onwards), after `data = json.loads(message)`, add new dispatch before the existing `if data.get("type") == "call_start":` check:

```python
                if data.get("type") == "speech_start":
                    stt_resample_state = None
                    stt._buffer.clear()
                    continue
                if data.get("type") == "speech_end":
                    if stt.has_utterance():
                        chunk = stt.take_utterance()
                        stt_resample_state = None
                        asyncio.create_task(_start_pipeline(chunk))
                    else:
                        stt._buffer.clear()
                        stt_resample_state = None
                    continue
```

(The `continue` keywords let the existing `if data.get("type") == "call_start":` chain stay as-is.)

- [ ] **Step 4: Smoke-test import + syntax**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -c "import ai_server" && python -m py_compile ai_server.py
```

Expected: no exception.

- [ ] **Step 5: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/ai_server.py
git commit -m "feat(stt): drive pipeline from RPi speech_start/speech_end markers"
```

---

## Task 9: Update standalone providers/stt_whisper.py

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/providers/stt_whisper.py`

- [ ] **Step 1: Remove RMS VAD block and flip vad_filter=False**

Replace the full contents of `providers/stt_whisper.py` with:

```python
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
```

- [ ] **Step 2: Smoke-test import**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -c "import providers.stt_whisper"
```

Expected: no exception.

- [ ] **Step 3: Commit**

```bash
git add 32GSMgatewayServer/tests/ari_test/providers/stt_whisper.py
git commit -m "refactor(stt-whisper): remove RMS VAD, drive transcribe from end_of_utterance"
```

---

## Task 10: End-to-end manual smoke test

**Files:**
- None (manual verification)

- [ ] **Step 1: Verify unit tests still pass**

```bash
cd 32GSMgatewayServer/tests/ari_test && python -m pytest test_silero_vad.py -v
```

Expected: 7 passing.

- [ ] **Step 2: Run ai_server.py on dev PC**

```bash
cd 32GSMgatewayServer/tests/ari_test && python ai_server.py
```

Expected: starts listening on port 9090, no import errors.

- [ ] **Step 3: Deploy bridge to RPi**

From repo root:

```bash
rsync -av 32GSMgatewayServer/tests/ari_test/ pi@<rpi-ip>:/home/pi/ari_test/
ssh pi@<rpi-ip> 'cd ~/ari_test && pip install -r requirements_test.txt'
```

Expected: files sync'd, `onnxruntime` installed on Pi.

- [ ] **Step 4: Place one real call**

On the Pi:

```bash
cd ~/ari_test && python rpi_audio_bridge.py \
    --endpoint "PJSIP/<test-number>@1017" \
    --server "ws://<dev-pc-ip>:9090"
```

Expected in logs:
- Pi: `Silero VAD loaded`, then during the call: `speech_start` / `speech_end` messages sent
- PC: `Audio bracketed: buf=...` during speech; one `STT: transcribing Xs` per utterance; intelligible transcripts

- [ ] **Step 5: Log Silero per-frame inference time (perf check)**

Before the call, add one-line perf probe at the top of `VADGate._on_frame` in `silero_vad.py`:

```python
    def _on_frame(self, frame, ulaw_chunk: bytes):
        import time as _t; _t0 = _t.monotonic()
        prob = self._stream.process(frame)
        _dt_ms = (_t.monotonic() - _t0) * 1000
        if _dt_ms > 10:
            import logging; logging.getLogger("silero").warning(f"frame took {_dt_ms:.1f}ms")
        is_speech = prob >= SPEECH_THRESHOLD
        ...
```

Expected: no warnings on Pi4/5 (per-frame typical < 10 ms). Remove the probe after verification.

- [ ] **Step 6: Final commit of any fixes**

If Steps 4–5 surface issues, address them with targeted fixes and commit:

```bash
git add <files> && git commit -m "fix(vad): <specific issue>"
```

If no issues, the implementation is complete.
