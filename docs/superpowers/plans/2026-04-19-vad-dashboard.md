# VAD Live Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve a live VAD debugging dashboard from the RPi audio bridge on port 3003. Browser connects, receives Silero probabilities, state transitions, and call lifecycle events over WebSocket, renders charts and an utterance log in real time.

**Architecture:** `VADGate` gains an optional `on_metrics` callback fired every frame with prob/max_abs/rms/latency/state. A new `Dashboard` class runs in its own thread inside `rpi_audio_bridge.py`, hosts a `websockets.serve` on 3003, short-circuits HTTP requests to serve static `index.html` + `app.js`, and fans out an internal queue to all connected WS clients. The dashboard never blocks the VAD path — pushes are non-blocking and drop silently when the queue is full.

**Tech Stack:** Python 3.12, `websockets>=12`, `numpy`, vanilla JS + Chart.js from CDN.

**Reference spec:** `docs/superpowers/specs/2026-04-19-vad-dashboard-design.md`

---

## File Structure

| File | Change | Purpose |
|---|---|---|
| `32GSMgatewayServer/tests/ari_test/requirements_test.txt` | **Modify** | Add `websockets>=12.0` |
| `32GSMgatewayServer/tests/ari_test/silero_vad.py` | **Modify** | Add `on_metrics` callback to `VADGate`, `last_utterance_ms()` |
| `32GSMgatewayServer/tests/ari_test/test_silero_vad.py` | **Modify** | New tests for metrics + utterance duration |
| `32GSMgatewayServer/tests/ari_test/vad_dashboard.py` | **Create** | `Dashboard` class — WS server thread + static HTTP |
| `32GSMgatewayServer/tests/ari_test/test_vad_dashboard.py` | **Create** | Unit tests for queue drop + event broadcast |
| `32GSMgatewayServer/tests/ari_test/dashboard/index.html` | **Create** | Page shell |
| `32GSMgatewayServer/tests/ari_test/dashboard/app.js` | **Create** | Chart.js + WS client |
| `32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py` | **Modify** | Instantiate Dashboard, wire callbacks, push call_start/end |

---

## Task 1: Add `websockets` dependency

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/requirements_test.txt`

- [ ] **Step 1: Add dep line**

Replace the VAD section block so the file reads:

```
# Core — ARI + RTP
requests>=2.28
websocket-client>=1.5
pyyaml>=6.0

# VAD — Silero v5 (runs on RPi)
onnxruntime>=1.17
numpy>=1.24

# Dashboard — WebSocket + HTTP on Pi, port 3003
websockets>=12.0

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

- [ ] **Step 2: Install on dev PC**

Run:
```bash
python3 -c "import websockets; print(websockets.__version__)"
```
Expected: prints a version string (already installed for `ai_server.py`). If `ModuleNotFoundError`, run `pip install --break-system-packages "websockets>=12.0"`.

- [ ] **Step 3: Install on RPi**

Run:
```bash
ssh pi@192.168.8.59 'python3 -c "import websockets; print(websockets.__version__)"' || \
ssh pi@192.168.8.59 'pip install --break-system-packages "websockets>=12.0"'
```
Expected: version printed, or install completes.

- [ ] **Step 4: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/requirements_test.txt
git commit -m "build(vad-dashboard): add websockets dep for RPi VAD monitor"
```

---

## Task 2: `VADGate.on_metrics` callback + frame metrics

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/silero_vad.py`
- Modify: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing test**

Append to `test_silero_vad.py`:

```python
def test_vad_gate_on_metrics_fires_per_frame(monkeypatch):
    """on_metrics callback must fire exactly once per _on_frame call,
    with all dashboard keys populated."""
    metrics = []

    monkeypatch.setattr(silero_vad.SileroStream, "process", lambda self, f: 0.0)

    gate = silero_vad.VADGate(
        on_speech_start=lambda: None,
        on_speech_audio=lambda b: None,
        on_speech_end=lambda: None,
        on_metrics=metrics.append,
    )

    frame = np.zeros(512, dtype=np.float32)
    gate._on_frame(frame, b"\x7f" * 320)
    gate._on_frame(frame, b"\x7f" * 320)

    assert len(metrics) == 2
    for m in metrics:
        assert m["type"] == "frame"
        assert set(["t", "frame", "prob", "max_abs", "rms",
                    "latency_ms", "state"]).issubset(m.keys())
        assert m["state"] in ("idle", "speaking")
        assert isinstance(m["prob"], float)
        assert isinstance(m["latency_ms"], float)

    assert metrics[0]["frame"] == 1
    assert metrics[1]["frame"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -m pytest test_silero_vad.py::test_vad_gate_on_metrics_fires_per_frame -v
```
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'on_metrics'`.

- [ ] **Step 3: Add the callback + metrics**

In `silero_vad.py`, modify the `VADGate.__init__` signature and body, and update `_on_frame` to compute metrics and invoke the callback.

Replace the block beginning with `class VADGate:` through the end of `_on_frame` with:

```python
class VADGate:
    """Full pipeline: ulaw bytes → resample → silero → state machine → callbacks.

    Callbacks:
      on_speech_start():             called once at utterance onset
      on_speech_audio(ulaw: bytes):  called for each ulaw chunk while SPEAKING
      on_speech_end():               called once at utterance offset
      on_metrics(event: dict):       optional; fired every frame with
                                     {type, t, frame, prob, max_abs, rms,
                                      latency_ms, state}. Must not raise.
    """

    def __init__(
        self,
        on_speech_start: Callable[[], None],
        on_speech_audio: Callable[[bytes], None],
        on_speech_end: Callable[[], None],
        on_metrics: Callable[[dict], None] | None = None,
    ):
        self._on_start = on_speech_start
        self._on_audio = on_speech_audio
        self._on_end = on_speech_end
        self._on_metrics = on_metrics
        self._stream = SileroStream()
        self._frames = UlawTo16kFrames()
        self._state = STATE_IDLE
        self._consec_speech = 0
        self._consec_silence = 0
        self._speech_frame_count = 0
        self._pending_ulaw = bytearray()
        self._frame_count = 0
        self._utterance_start_t = 0.0
        self._last_utterance_ms = 0.0

    def reset(self):
        """Call at the start of a new call. Resets VAD state + LSTM."""
        self._stream.reset()
        self._frames.reset()
        self._state = STATE_IDLE
        self._consec_speech = 0
        self._consec_silence = 0
        self._speech_frame_count = 0
        self._pending_ulaw.clear()
        self._frame_count = 0
        self._utterance_start_t = 0.0
        self._last_utterance_ms = 0.0

    def is_speaking(self) -> bool:
        return self._state == STATE_SPEAKING

    def last_utterance_ms(self) -> float:
        """Duration of the most recent completed utterance in milliseconds.
        Zero if no utterance has completed yet."""
        return self._last_utterance_ms

    def feed(self, ulaw_chunk: bytes):
        """Feed raw ulaw bytes from RTP. Drives the VAD pipeline and callbacks."""
        for frame in self._frames.feed(ulaw_chunk):
            self._on_frame(frame, ulaw_chunk)

    def _on_frame(self, frame, ulaw_chunk: bytes):
        import time as _time

        self._frame_count += 1
        t0 = _time.monotonic()
        prob = self._stream.process(frame)
        latency_ms = (_time.monotonic() - t0) * 1000.0
        is_speech = prob >= SPEECH_THRESHOLD

        prev_state = self._state
        entered_speaking = False
        left_speaking = False

        if self._state == STATE_IDLE:
            self._pending_ulaw.extend(ulaw_chunk)
            if len(self._pending_ulaw) > 1600:
                del self._pending_ulaw[:-1600]

            if is_speech:
                self._consec_speech += 1
                if self._consec_speech >= ONSET_FRAMES:
                    self._state = STATE_SPEAKING
                    self._speech_frame_count = self._consec_speech
                    self._consec_silence = 0
                    self._utterance_start_t = _time.monotonic()
                    entered_speaking = True
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
                    self._last_utterance_ms = (_time.monotonic() - self._utterance_start_t) * 1000.0
                    self._state = STATE_IDLE
                    self._consec_speech = 0
                    self._consec_silence = 0
                    self._speech_frame_count = 0
                    self._pending_ulaw.clear()
                    left_speaking = True
                    if emitted_end:
                        self._on_end()

        if self._on_metrics is not None:
            # Compute audio stats on the new frame (float32 [-1, 1])
            max_abs = float(np.abs(frame).max())
            rms = float(np.sqrt(np.mean(frame * frame)))
            try:
                self._on_metrics({
                    "type": "frame",
                    "t": _time.monotonic() * 1000.0,
                    "frame": self._frame_count,
                    "prob": float(prob),
                    "max_abs": max_abs,
                    "rms": rms,
                    "latency_ms": latency_ms,
                    "state": self._state,
                })
            except Exception:
                # Metrics must never break the VAD path
                pass
```

- [ ] **Step 4: Run the new test**

```bash
python3 -m pytest test_silero_vad.py::test_vad_gate_on_metrics_fires_per_frame -v
```
Expected: PASS.

- [ ] **Step 5: Run the full suite to catch regressions**

```bash
python3 -m pytest test_silero_vad.py -v
```
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/silero_vad.py \
        32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "feat(vad): add on_metrics callback + utterance duration to VADGate"
```

---

## Task 3: `VADGate.last_utterance_ms()` regression test

The behavior was added in Task 2. Add a focused test so it can't silently break.

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/test_silero_vad.py`

- [ ] **Step 1: Write the failing (or passing, but previously untested) test**

Append to `test_silero_vad.py`:

```python
def test_vad_gate_last_utterance_ms_populated_after_speech_end(monkeypatch):
    """After a full speech_start → ... → speech_end cycle,
    last_utterance_ms() must report a positive duration."""
    # Use a mutable probability source so we can script the transitions
    probs = iter([0.9] * 5 + [0.1] * 30)

    def mock_process(self, frame):
        return next(probs, 0.0)

    monkeypatch.setattr(silero_vad.SileroStream, "process", mock_process)

    gate = silero_vad.VADGate(
        on_speech_start=lambda: None,
        on_speech_audio=lambda b: None,
        on_speech_end=lambda: None,
    )

    frame = np.zeros(512, dtype=np.float32)
    for _ in range(35):
        gate._on_frame(frame, b"\x7f" * 320)

    assert not gate.is_speaking()
    assert gate.last_utterance_ms() > 0, \
        f"expected positive utterance duration, got {gate.last_utterance_ms()}"
```

- [ ] **Step 2: Run**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -m pytest test_silero_vad.py::test_vad_gate_last_utterance_ms_populated_after_speech_end -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/test_silero_vad.py
git commit -m "test(vad): regression for last_utterance_ms() duration"
```

---

## Task 4: `Dashboard.push()` — bounded queue that drops silently

**Files:**
- Create: `32GSMgatewayServer/tests/ari_test/vad_dashboard.py`
- Create: `32GSMgatewayServer/tests/ari_test/test_vad_dashboard.py`

- [ ] **Step 1: Write the failing test**

Create `test_vad_dashboard.py`:

```python
"""Unit tests for vad_dashboard module (queue-drop only;
networking smoke-tested manually)."""
import pytest

import vad_dashboard


def test_dashboard_push_does_not_block_when_queue_full():
    """Dashboard.push() must never raise or block, even with no consumer."""
    dash = vad_dashboard.Dashboard(host="127.0.0.1", port=0, queue_max=5)
    # No threads started — nothing drains the queue.
    for i in range(100):
        dash.push({"type": "frame", "i": i})  # must not raise
    # The queue is capped; only the first `queue_max` items made it in.
    assert dash._queue.qsize() <= 5


def test_dashboard_push_accepts_dicts_only():
    """Dashboard.push() must not be called with non-dict; surface a clear error."""
    dash = vad_dashboard.Dashboard(host="127.0.0.1", port=0, queue_max=5)
    with pytest.raises(TypeError):
        dash.push("not a dict")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -m pytest test_vad_dashboard.py -v
```
Expected: FAIL — `ModuleNotFoundError: vad_dashboard`.

- [ ] **Step 3: Minimal implementation**

Create `vad_dashboard.py`:

```python
"""VAD live dashboard — HTTP + WebSocket server for browser monitor.

Runs in its own daemon thread with its own asyncio loop, so it never blocks
the RTP/VAD path. Use Dashboard.push(event: dict) from any thread.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional


class Dashboard:
    """Event bus + web server for the VAD monitor page.

    Thread model:
      - Constructor does nothing heavyweight.
      - .start() spawns a daemon thread running an asyncio loop.
      - .push(event) is thread-safe (queue.put_nowait). Drops silently when full.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 3003,
                 queue_max: int = 500):
        self._host = host
        self._port = port
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=queue_max)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def push(self, event: dict) -> None:
        """Queue a JSON-serializable event dict. Never blocks, drops on overflow."""
        if not isinstance(event, dict):
            raise TypeError(f"Dashboard event must be a dict, got {type(event).__name__}")
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass  # drop

    def start(self) -> None:
        """Spawn the server thread. Idempotent."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="vad-dashboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Server loop stub — filled in by Task 5.
        pass
```

- [ ] **Step 4: Run**

```bash
python3 -m pytest test_vad_dashboard.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/vad_dashboard.py \
        32GSMgatewayServer/tests/ari_test/test_vad_dashboard.py
git commit -m "feat(vad-dashboard): Dashboard class with bounded drop-on-full queue"
```

---

## Task 5: Dashboard server — asyncio loop, WS broadcaster, hello

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/vad_dashboard.py`

- [ ] **Step 1: Extend the module**

Replace `vad_dashboard.py` with:

```python
"""VAD live dashboard — HTTP + WebSocket server for browser monitor.

Runs in its own daemon thread with its own asyncio loop, so it never blocks
the RTP/VAD path. Use Dashboard.push(event: dict) from any thread.
"""
from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from pathlib import Path
from typing import Optional, Set

log = logging.getLogger(__name__)

# Populated lazily from the bridge (Task 8) so /hello can report current config
HELLO_DEFAULTS = {
    "type": "hello",
    "bridge_state": "idle",
    "threshold": 0.5,
    "onset_frames": 2,
    "offset_frames": 25,
}


class Dashboard:
    """Event bus + web server for the VAD monitor page."""

    def __init__(self, host: str = "0.0.0.0", port: int = 3003,
                 queue_max: int = 500,
                 static_dir: Optional[Path] = None):
        self._host = host
        self._port = port
        self._queue: queue.Queue[dict] = queue.Queue(maxsize=queue_max)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Set = set()
        self._static_dir = static_dir or (Path(__file__).parent / "dashboard")
        self._hello = dict(HELLO_DEFAULTS)

    def push(self, event: dict) -> None:
        if not isinstance(event, dict):
            raise TypeError(f"Dashboard event must be a dict, got {type(event).__name__}")
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            pass

    def update_hello(self, **kwargs) -> None:
        """Update the snapshot sent to newly connected browsers. Thread-safe."""
        self._hello.update(kwargs)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="vad-dashboard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ── server ──
    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"Dashboard server crashed: {e}")
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        import websockets

        async def handler(ws):
            self._clients.add(ws)
            try:
                # Send hello snapshot so a mid-call reload recovers state
                hello = dict(self._hello)
                hello["t"] = _now_ms()
                await ws.send(json.dumps(hello))
                # Keep connection alive; we never read from the browser
                async for _ in ws:
                    pass
            finally:
                self._clients.discard(ws)

        async def process_request(path, request_headers):
            return await self._serve_static(path, request_headers)

        # websockets>=12 signature varies; fall back gracefully
        try:
            async with websockets.serve(
                handler, self._host, self._port,
                process_request=process_request,
            ) as server:
                log.info(f"[DASH] Listening on http://{self._host}:{self._port}/")
                await asyncio.gather(self._broadcaster(), self._wait_stop())
                server.close()
        except TypeError:
            # Older/newer websockets with a different serve() signature
            async with websockets.serve(handler, self._host, self._port) as server:
                log.warning("[DASH] process_request unavailable — /stream only")
                await asyncio.gather(self._broadcaster(), self._wait_stop())
                server.close()

    async def _wait_stop(self):
        while not self._stop.is_set():
            await asyncio.sleep(0.25)

    async def _broadcaster(self):
        """Drain the thread-safe queue and fan-out to WS clients."""
        while not self._stop.is_set():
            try:
                event = await asyncio.get_event_loop().run_in_executor(
                    None, self._queue.get, True, 0.25)
            except queue.Empty:
                continue
            if event is None:
                continue
            msg = json.dumps(event)
            dead = []
            for ws in list(self._clients):
                try:
                    await ws.send(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    async def _serve_static(self, path: str, headers):
        """Return an HTTP response tuple for known static paths, else None
        so websockets proceeds with the WS upgrade."""
        path = path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return _file_response(self._static_dir / "index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return _file_response(self._static_dir / "app.js", "application/javascript; charset=utf-8")
        if path == "/stream":
            return None  # let WS upgrade proceed
        return (404, [("Content-Type", "text/plain")], b"not found")


def _file_response(path: Path, content_type: str):
    try:
        body = path.read_bytes()
        return (200, [("Content-Type", content_type),
                      ("Cache-Control", "no-store")], body)
    except FileNotFoundError:
        return (500, [("Content-Type", "text/plain")], f"missing: {path}".encode())


def _now_ms() -> float:
    import time
    return time.monotonic() * 1000.0
```

- [ ] **Step 2: Smoke-test the module import + start/stop**

Run this ad-hoc check (do not add as a unit test — it depends on a free port):

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -c "
import time, vad_dashboard
d = vad_dashboard.Dashboard(host='127.0.0.1', port=3004)
d.start()
time.sleep(0.5)
d.push({'type':'frame','prob':0.7})
time.sleep(0.2)
d.stop()
print('OK')
"
```
Expected: prints `OK` and `[DASH] Listening on http://127.0.0.1:3004/` in logs; no exception.

- [ ] **Step 3: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/vad_dashboard.py
git commit -m "feat(vad-dashboard): WS broadcaster + static HTTP on port 3003"
```

---

## Task 6: Dashboard UI — HTML shell

**Files:**
- Create: `32GSMgatewayServer/tests/ari_test/dashboard/index.html`

- [ ] **Step 1: Create the page**

Create `32GSMgatewayServer/tests/ari_test/dashboard/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>VAD Live Monitor</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root { --bg:#0f1117; --card:#1a2035; --edge:#1e2d4a; --text:#e2e8f0;
          --dim:#94a3b8; --green:#22c55e; --amber:#fbbf24; --red:#ef4444; }
  * { box-sizing: border-box; font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }
  body { background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
  h1 { font-size: 18px; margin: 0 0 14px 0; display: flex; justify-content: space-between; align-items: center; }
  h1 small { color: var(--dim); font-weight: normal; font-size: 12px; }
  .row { display: flex; gap: 16px; margin-bottom: 16px; }
  .card { background: var(--card); border: 1px solid var(--edge); border-radius: 10px; padding: 14px; }
  #state-card { min-width: 200px; text-align: center; }
  #state-label { font-size: 13px; color: var(--dim); margin-bottom: 6px; }
  #state-value { font-size: 28px; font-weight: 700; letter-spacing: 1px; }
  .state-idle { color: var(--dim); }
  .state-speaking { color: var(--green); }
  #info-card { flex: 1; }
  #info-card .k { color: var(--dim); display: inline-block; min-width: 100px; }
  #info-card .v { color: var(--text); }
  #info-card div { margin: 2px 0; font-size: 13px; }
  .chart-card { background: var(--card); border: 1px solid var(--edge); border-radius: 10px; padding: 10px 14px; margin-bottom: 14px; }
  .chart-card h2 { font-size: 12px; color: var(--dim); margin: 0 0 6px 0; font-weight: 500; }
  .chart-wrap { height: 140px; position: relative; }
  #utterance-log { max-height: 220px; overflow-y: auto; }
  #utterance-log .ent { padding: 5px 2px; border-bottom: 1px solid #121826; font-size: 13px; display: flex; gap: 12px; }
  #utterance-log .ent .ts { color: var(--dim); width: 80px; }
  #utterance-log .ent .dur { color: var(--green); }
  #conn { font-size: 11px; padding: 2px 8px; border-radius: 4px; }
  #conn.up { background: #064e3b; color: var(--green); }
  #conn.down { background: #450a0a; color: var(--red); }
</style>
</head>
<body>
  <h1>
    VAD Live Monitor
    <small>Pi: <span id="pi-host">—</span> · <span id="conn" class="down">disconnected</span></small>
  </h1>

  <div class="row">
    <div class="card" id="state-card">
      <div id="state-label">STATE</div>
      <div id="state-value" class="state-idle">IDLE</div>
    </div>
    <div class="card" id="info-card">
      <div><span class="k">Bridge:</span>    <span class="v" id="bridge-state">idle</span></div>
      <div><span class="k">Call:</span>      <span class="v" id="call-info">—</span></div>
      <div><span class="k">Duration:</span>  <span class="v" id="duration">00:00</span></div>
      <div><span class="k">Frames:</span>    <span class="v" id="frames">0</span></div>
      <div><span class="k">Latency:</span>   <span class="v" id="latency">—</span></div>
      <div><span class="k">Threshold:</span> <span class="v" id="threshold">0.50</span></div>
    </div>
  </div>

  <div class="chart-card">
    <h2>Speech probability (last 10 s)</h2>
    <div class="chart-wrap"><canvas id="prob-chart"></canvas></div>
  </div>

  <div class="chart-card">
    <h2>Max-abs amplitude (last 10 s)</h2>
    <div class="chart-wrap"><canvas id="amp-chart"></canvas></div>
  </div>

  <div class="card">
    <h2 style="font-size:12px;color:var(--dim);margin:0 0 8px 0;">Utterance log (newest first)</h2>
    <div id="utterance-log"></div>
  </div>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/dashboard/index.html
git commit -m "feat(vad-dashboard): HTML shell for live monitor page"
```

---

## Task 7: Dashboard UI — JS client

**Files:**
- Create: `32GSMgatewayServer/tests/ari_test/dashboard/app.js`

- [ ] **Step 1: Create the client script**

Create `32GSMgatewayServer/tests/ari_test/dashboard/app.js`:

```javascript
(() => {
  const WINDOW_MS = 10_000;
  const host = location.host;
  document.getElementById('pi-host').textContent = host;

  // ---- Charts
  function mkChart(id, color) {
    const ctx = document.getElementById(id).getContext('2d');
    return new Chart(ctx, {
      type: 'line',
      data: { datasets: [{
        data: [], borderColor: color, backgroundColor: color + '33',
        borderWidth: 1.2, pointRadius: 0, tension: 0.15, fill: true,
      }]},
      options: {
        animation: false, responsive: true, maintainAspectRatio: false,
        parsing: false, normalized: true,
        scales: {
          x: { type: 'linear', ticks: { color: '#94a3b8', maxTicksLimit: 6 },
               grid: { color: '#1e2d4a' } },
          y: { min: 0, max: 1, ticks: { color: '#94a3b8' },
               grid: { color: '#1e2d4a' } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  const probChart = mkChart('prob-chart', '#60a5fa');
  const ampChart  = mkChart('amp-chart',  '#22c55e');

  function pushPoint(chart, t, v) {
    const d = chart.data.datasets[0].data;
    d.push({ x: t, y: v });
    const cutoff = t - WINDOW_MS;
    while (d.length && d[0].x < cutoff) d.shift();
    chart.update('none');
  }

  // ---- DOM handles
  const els = {
    stateValue:  document.getElementById('state-value'),
    bridge:      document.getElementById('bridge-state'),
    callInfo:    document.getElementById('call-info'),
    duration:    document.getElementById('duration'),
    frames:      document.getElementById('frames'),
    latency:     document.getElementById('latency'),
    threshold:   document.getElementById('threshold'),
    log:         document.getElementById('utterance-log'),
    conn:        document.getElementById('conn'),
  };

  let callStartT = 0;
  let frameCount = 0;
  let latSum = 0, latMax = 0;
  let durTimer = null;

  function fmtDur(ms) {
    const s = Math.floor(ms / 1000);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  function setState(state) {
    els.stateValue.textContent = state.toUpperCase();
    els.stateValue.className = 'state-' + state;
  }

  function addUtterance(ms) {
    const now = new Date();
    const stamp = now.toTimeString().slice(0, 8);
    const row = document.createElement('div');
    row.className = 'ent';
    row.innerHTML = `<span class="ts">${stamp}</span>` +
                    `<span>speech</span>` +
                    `<span class="dur">${(ms / 1000).toFixed(2)}s</span>`;
    els.log.insertBefore(row, els.log.firstChild);
    while (els.log.children.length > 50) els.log.lastChild.remove();
  }

  // ---- WS connection
  function connect() {
    const url = `ws://${location.host}/stream`;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      els.conn.className = 'up';
      els.conn.textContent = 'connected';
    };
    ws.onclose = () => {
      els.conn.className = 'down';
      els.conn.textContent = 'disconnected — retrying';
      setTimeout(connect, 1500);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      handle(ev);
    };
  }

  function handle(ev) {
    switch (ev.type) {
      case 'hello':
        els.bridge.textContent = ev.bridge_state || 'idle';
        els.threshold.textContent = (ev.threshold ?? 0.5).toFixed(2);
        break;
      case 'frame':
        frameCount = ev.frame ?? (frameCount + 1);
        els.frames.textContent = frameCount;
        latSum += ev.latency_ms; latMax = Math.max(latMax, ev.latency_ms);
        els.latency.textContent =
          `${(latSum / frameCount).toFixed(1)} ms avg / ${latMax.toFixed(1)} max`;
        pushPoint(probChart, ev.t, ev.prob);
        pushPoint(ampChart,  ev.t, ev.max_abs);
        setState(ev.state);
        break;
      case 'speech_start':
        setState('speaking');
        break;
      case 'speech_end':
        setState('idle');
        if (ev.duration_ms) addUtterance(ev.duration_ms);
        break;
      case 'call_start':
        callStartT = Date.now();
        els.bridge.textContent = 'in_call';
        els.callInfo.textContent =
          `${ev.endpoint || '—'} (${ev.mode || '—'})`;
        frameCount = 0; latSum = 0; latMax = 0;
        if (durTimer) clearInterval(durTimer);
        durTimer = setInterval(() => {
          els.duration.textContent = fmtDur(Date.now() - callStartT);
        }, 500);
        break;
      case 'call_end':
        els.bridge.textContent = 'idle';
        if (durTimer) { clearInterval(durTimer); durTimer = null; }
        break;
    }
  }

  connect();
})();
```

- [ ] **Step 2: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/dashboard/app.js
git commit -m "feat(vad-dashboard): JS client with prob/amp charts + utterance log"
```

---

## Task 8: Wire Dashboard into `rpi_audio_bridge.py`

**Files:**
- Modify: `32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py`

- [ ] **Step 1: Add import + construct Dashboard**

Open `rpi_audio_bridge.py`. Near the top of the file, add an import next to `import silero_vad`:

```python
import silero_vad
from vad_dashboard import Dashboard
```

- [ ] **Step 2: Start dashboard in `main()`, wire callbacks**

Locate the block (added in an earlier change) that reads:

```python
    vad = silero_vad.VADGate(
        on_speech_start=lambda: _send_json({"type": "speech_start"}),
        on_speech_audio=_send_ulaw,
        on_speech_end=lambda: _send_json({"type": "speech_end"}),
    )
```

Replace it with a version that starts the dashboard and wires callbacks to it as well:

```python
    dash = Dashboard(host="0.0.0.0", port=3003)
    dash.update_hello(
        threshold=silero_vad.SPEECH_THRESHOLD,
        onset_frames=silero_vad.ONSET_FRAMES,
        offset_frames=silero_vad.OFFSET_FRAMES,
    )
    dash.start()
    print(f"[DASH] http://0.0.0.0:3003/")

    def _on_speech_start():
        _send_json({"type": "speech_start"})
        dash.push({"type": "speech_start"})

    def _on_speech_end():
        _send_json({"type": "speech_end"})
        dash.push({"type": "speech_end",
                   "duration_ms": vad.last_utterance_ms()})

    vad = silero_vad.VADGate(
        on_speech_start=_on_speech_start,
        on_speech_audio=_send_ulaw,
        on_speech_end=_on_speech_end,
        on_metrics=dash.push,
    )
```

- [ ] **Step 3: Push call lifecycle to dashboard**

Locate the `on_call_start` / `on_call_end` callbacks defined earlier in `main()`. Replace them with:

```python
    # ARI callbacks
    def on_call_start(is_incoming, caller):
        vad.reset()
        dash.update_hello(bridge_state="in_call")
        dash.push({
            "type": "call_start",
            "mode": "incoming" if is_incoming else "outbound",
            "endpoint": args.endpoint or "incoming",
            "caller": caller,
        })
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
        if vad.is_speaking():
            _send_json({"type": "speech_end"})
        vad.reset()
        dash.update_hello(bridge_state="idle")
        dash.push({"type": "call_end"})
        rtp.flush_queue()
        if ai_ws:
            ai_ws.send(json.dumps({"type": "call_end"}))
```

- [ ] **Step 4: Smoke-test import**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -c "import rpi_audio_bridge; print('OK')"
```
Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add 32GSMgatewayServer/tests/ari_test/rpi_audio_bridge.py
git commit -m "feat(vad-dashboard): wire Dashboard into RPi bridge"
```

---

## Task 9: Manual end-to-end smoke test on the RPi

**Files:** — none (manual verification)

- [ ] **Step 1: Sync to Pi**

```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
rsync -av --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.db' --exclude 'venv_vad' \
  32GSMgatewayServer/tests/ari_test/ pi@192.168.8.59:/home/pi/Documents/32GSMgatewayServer/tests/ari_test/
```
Expected: new files (`vad_dashboard.py`, `dashboard/index.html`, `dashboard/app.js`) synced; updated `silero_vad.py`, `rpi_audio_bridge.py`, `requirements_test.txt`.

- [ ] **Step 2: Ensure `websockets` installed on Pi**

```bash
ssh pi@192.168.8.59 'python3 -c "import websockets; print(websockets.__version__)"' || \
ssh pi@192.168.8.59 'pip install --break-system-packages "websockets>=12.0"'
```
Expected: version printed.

- [ ] **Step 3: Start `ai_server.py` on dev PC**

In a terminal on the dev PC:
```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd/32GSMgatewayServer/tests/ari_test
python3 -u ai_server.py > /tmp/ai_server.log 2>&1 &
```
Wait until the log prints `AI Server listening on 0.0.0.0:9090`.

- [ ] **Step 4: Start the bridge on the Pi**

```bash
ssh pi@192.168.8.59 '~/Documents/32GSMgatewayServer/tests/ari_test/run_bridge.sh --mode outbound --endpoint "PJSIP/8757839258@1017" --server "ws://192.168.8.7:9090"' > /tmp/rpi_bridge.log 2>&1 &
```
Wait for `[DASH] http://0.0.0.0:3003/` and `[AI-WS] Connected` in `/tmp/rpi_bridge.log`.

- [ ] **Step 5: Open the dashboard in a browser**

On the dev PC, open `http://192.168.8.59:3003/`.

Expected (before answering):
- Connection indicator turns green (`connected`).
- State box reads `IDLE`.
- Threshold reads `0.50`, Bridge `idle`.

- [ ] **Step 6: Answer the call and speak**

Expected while speaking:
- `Bridge` turns `in_call`, `Call` shows the endpoint, `Duration` ticks up.
- Probability chart rises above the 0.5 threshold and the amplitude chart reacts.
- State box turns green (`SPEAKING`) during speech, back to grey on silence.
- A new entry appears in Utterance log with duration.
- `Latency` stays under `10 ms avg` on a Pi4/5.

- [ ] **Step 7: Hang up**

Expected: `Bridge` returns to `idle`, duration timer stops. Browser stays connected (ready for next call).

- [ ] **Step 8: Commit any fixes**

If Steps 5–7 surface issues, fix them and commit:
```bash
cd /home/ubuntu/Documents/SabkiappDigiCampProd
git add <changed files>
git commit -m "fix(vad-dashboard): <specific issue>"
```

If no issues, mark implementation complete.
