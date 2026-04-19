# VAD Live Dashboard — Design

**Date**: 2026-04-19
**Scope**: Live browser dashboard served by the RPi audio bridge on port 3003. Streams real-time Silero VAD metrics (probabilities, state, events) over WebSocket while a call is in progress. Read-only visualization for debugging — no TTS, no call control.

**Audience**: developer on the same LAN as the RPi. Open `http://192.168.8.59:3003/` in a browser during a call.

**Reference**: follow-on work to `2026-04-19-silero-vad-v5-rpi-design.md`.

---

## 1. Architecture

```
rpi_audio_bridge.py  (main thread — unchanged RTP + VAD path)
  VADGate
    ├─ on_speech_start/audio/end  → existing WS to ai_server (PC)
    └─ on_metrics(prob, max_abs,  → dashboard.push()
                  rms, latency_ms,
                  state)

vad_dashboard.py  (NEW — own thread, own asyncio loop)
  ├─ websockets.serve(0.0.0.0:3003)
  │   ├─ GET /        → serves dashboard/index.html
  │   ├─ GET /app.js  → serves dashboard/app.js
  │   └─ WS  /stream  → broadcast events to all connected browsers
  ├─ event_queue      (thread-safe, bounded)
  └─ broadcaster task pops queue → fan-out to connected clients

dashboard/
  ├─ index.html    (page shell — dark theme)
  └─ app.js        (Chart.js + WS client, updates UI)
```

**Key invariant**: the dashboard never blocks the RTP path. `Dashboard.push()` is a `queue.put_nowait` — drops silently when the queue is full. If a browser disconnects mid-call, the VAD pipeline is unaffected.

**Thread model**: existing RTP / VAD / ARI code stays threading-based. The dashboard runs in its own thread with its own asyncio event loop; it pops from a `queue.Queue` fed by the VAD thread.

---

## 2. Event Protocol (JSON over WebSocket)

Every event is one JSON object with `t` = monotonic time in ms since Pi boot (so clock-skew across events is consistent even if wall clock jumps).

### Per-frame — ~31 events/sec while call active
```json
{"type":"frame", "t":12345678, "frame":1523, "prob":0.823,
 "max_abs":0.41, "rms":0.12, "latency_ms":4.2, "state":"speaking"}
```

### VAD transitions
```json
{"type":"speech_start", "t":12345678}
{"type":"speech_end",   "t":12345699, "duration_ms":1400}
```

### Call lifecycle
```json
{"type":"call_start", "t":12345000, "mode":"outbound",
 "endpoint":"PJSIP/8757839258@1017", "caller":"?"}
{"type":"call_end",   "t":12346000, "duration_s":50.2}
```

### On-connect snapshot (so browser reload recovers state)
```json
{"type":"hello", "t":12345000,
 "bridge_state":"idle|ringing|in_call",
 "threshold":0.5, "onset_frames":2, "offset_frames":25}
```

**Volume**: ~32 frame events/sec × ~70 bytes ≈ 2 KB/s per client. Trivial over LAN.

**Queue policy**: `Dashboard.event_queue` is bounded at 500 items. If full, new events are dropped silently. No back-pressure reaches the VAD path. The per-frame event itself is lossy-ok — the UI just skips a frame.

---

## 3. Dashboard UI

Single page, dark theme consistent with `call_manager.py` (`#0f1117` background, `#1a2035` cards, accent colors green / amber / red for state).

### Layout
```
┌─────────────────────────────────────────────────────────┐
│  VAD Live Monitor           Pi: 192.168.8.59:3003       │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌────────────────────────────────┐   │
│  │ STATE        │  │ Bridge:  in_call               │   │
│  │              │  │ Call:    PJSIP/…258 (outbound) │   │
│  │  SPEAKING    │  │ Duration: 00:24                │   │
│  │  (green)     │  │ Frames:  742                   │   │
│  └──────────────┘  │ Latency: 4.1 ms avg / 8.0 max  │   │
│                    │ Threshold: 0.50                │   │
│                    └────────────────────────────────┘   │
│                                                         │
│  Speech Probability (last 10s)                          │
│  [line chart, horizontal threshold dashed at 0.5]       │
│                                                         │
│  Max-abs amplitude (last 10s)                           │
│  [line chart, green]                                    │
│                                                         │
│  Utterance log (newest first, last 50)                  │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 18:15:55  speech  1.14s                         │   │
│  │ 18:15:47  speech  1.04s                         │   │
│  │ 18:15:36  speech  4.32s                         │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Tech
- Vanilla JS (no build step)
- Chart.js from CDN — two line charts sharing an X axis, 10 s rolling window, ~320 points each
- State box: CSS class swap on `speech_start` / `speech_end`
- Threshold line: drawn as a Chart.js annotation from the value in the `hello` event
- `speech_start` events drawn as vertical green ticks on the prob chart

### State recovery
On browser reload mid-call, the `hello` message on WS open carries the current bridge state so the UI resumes without a stale view. The rolling charts start empty — no historical buffer on the Pi.

---

## 4. Wiring, Dependencies, Launcher

### `silero_vad.py`
Add optional `on_metrics` callback to `VADGate`:

```python
def __init__(self, on_speech_start, on_speech_audio, on_speech_end,
             on_metrics=None):  # NEW — optional
    ...
```

Fires every frame with a `dict` of `{type:"frame", prob, max_abs, rms, latency_ms, state, frame}`. If `on_metrics is None`, behaviour is unchanged.

Also expose `VADGate.last_utterance_ms()` returning the duration of the most recent completed utterance, so the bridge can include it in the `speech_end` dashboard event.

### `rpi_audio_bridge.py`
Wire a `Dashboard` instance:

```python
from vad_dashboard import Dashboard
dash = Dashboard(host="0.0.0.0", port=3003)
dash.start()                         # spawn thread

vad = silero_vad.VADGate(
    on_speech_start=lambda: (_send_json({"type":"speech_start"}),
                             dash.push({"type":"speech_start"})),
    on_speech_audio=_send_ulaw,
    on_speech_end=lambda: (_send_json({"type":"speech_end"}),
                           dash.push({"type":"speech_end",
                                      "duration_ms": vad.last_utterance_ms()})),
    on_metrics=dash.push,
)

# Also push call_start / call_end from the ARI callbacks that already fire.
```

### `vad_dashboard.py` (new, ~150 LOC)
- `Dashboard(host, port)` with `.start()` (spawns daemon thread) and `.push(event: dict)` (thread-safe `queue.put_nowait`).
- Serves static `dashboard/index.html`, `dashboard/app.js`.
- WS `/stream`: on connect, emit `hello`, then broadcast every event from the queue to all connected clients.
- `on_metrics` events arrive with `type:"frame"` already set — no re-wrapping needed.

### Dependencies
Add to `32GSMgatewayServer/tests/ari_test/requirements_test.txt`:
```
websockets>=12.0
```
Already installed on the PC (used by `ai_server.py`). Needed on the Pi. Install via `pip install --break-system-packages websockets` (matches existing workflow).

### Launcher
Extend `run_bridge.sh` flag passthrough:
```bash
#!/bin/bash
export SILERO_MODEL_PATH="$(dirname "$(readlink -f "$0")")/models/silero_vad_v5.onnx"
export PYTHONUNBUFFERED=1
cd "$(dirname "$(readlink -f "$0")")"
exec python3 -u rpi_audio_bridge.py "$@"
```
(No change needed — `rpi_audio_bridge.py` adds `--dashboard / --no-dashboard` argparse flags; default on.)

### Testing
1. **Unit** — `Dashboard.push()` drops silently when queue full; no exception propagates.
2. **Unit** — `VADGate(on_metrics=f)` calls `f` exactly once per `_on_frame`, with required dict keys present.
3. **Unit** — `VADGate.last_utterance_ms()` returns correct duration after a speech_start/end sequence.
4. **Manual E2E** — start bridge on Pi, open `http://192.168.8.59:3003/` on dev PC, place a call, speak. Verify: `hello` on connect, prob chart moves, state box turns green on speech, utterance log grows, numbers match server-side logs.

---

## 5. Out of Scope

- Recording or exporting a session (live view only; close browser = data gone)
- Multi-call historical dashboard
- Authentication (LAN-only, trusted network)
- TTS output visualization (dashboard stays purely VAD-focused)
- Raw waveform playback (sends stats only, not audio samples — protocol permits extension later if needed)
- Dashboard failure handling beyond "dies with bridge": no watchdog, no auto-restart
