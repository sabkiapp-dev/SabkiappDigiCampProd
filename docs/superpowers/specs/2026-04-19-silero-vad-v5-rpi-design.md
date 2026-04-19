# Silero VAD v5 on RPi — Design

**Date**: 2026-04-19
**Scope**: Replace the custom RMS VAD (on PC) and the faster-whisper internal Silero VAD pass with a single Silero VAD v5 gate running on the RPi. All STT providers on the PC receive only speech — no local VAD on the PC side.

**Model source**: [`runanywhere/silero-vad-v5`](https://huggingface.co/runanywhere/silero-vad-v5) (ONNX, ~2.2 MB, MIT). Upstream: [snakers4/silero-vad](https://github.com/snakers4/silero-vad).

---

## 1. Motivation

Current pipeline runs VAD twice:

1. Custom RMS gate in `ai_server.py :: _STTBase.vad()` (hand-rolled, ~30 lines).
2. faster-whisper's internal Silero VAD (`vad_filter=True`, `stt_whisper.py` and `ai_server.py :: WhisperSTT._transcribe`).

Problems:
- Duplicate work, two thresholds to tune, inconsistent behavior across providers.
- RMS gate is crude (noise-floor-sensitive).
- All audio is forwarded from Pi to PC over the LAN even during silence.

This design consolidates VAD into **one Silero v5 pass on the RPi**, before any network transit.

---

## 2. Architecture

```
RPi                                             PC
RTP ulaw 20ms ─► ulaw2lin ─► 8k→16k resample ─► 512-sample buffer
                                                    │
                                              Silero(frame) → prob
                                                    │
                                              state machine
                                                    │
         ┌──────────────────────────────────────────┤
         ▼                         ▼                ▼
    speech_start (JSON)      ulaw frames (binary)   speech_end (JSON)
         │                         │                │
         └──────── WebSocket ──────┴────────────────┘
                                                    ▼
                                          PC: collect between markers
                                          → feed STT on speech_end
```

- **RPi owns VAD.** Runs Silero v5 ONNX on every 512-sample (32 ms @ 16 kHz) frame. Emits JSON markers + gated binary audio over the existing WS.
- **PC is passive.** `_STTBase` loses its VAD entirely and just buffers ulaw between markers, feeding the STT backend on `speech_end`.
- **Silero model**: single global `onnxruntime.InferenceSession` on the Pi, shared across calls. Each call has its own `SileroStream` holding per-call LSTM state. State resets on `call_start`.

---

## 3. Silero VAD Module

New file: `32GSMgatewayServer/tests/ari_test/silero_vad.py` (RPi-side).

### Responsibilities
- Load the ONNX model once (global singleton).
- Expose `SileroStream()` — per-call instance holding LSTM state.
- `stream.process(pcm16_16k_frame_512: bytes) -> prob: float`.
- `stream.reset()` — reset LSTM state on new call.

### Model fetch
- On first run, download from
  `https://huggingface.co/runanywhere/silero-vad-v5/resolve/main/silero_vad.onnx`
  to `~/.cache/silero/silero_vad_v5.onnx` (idempotent).
- `SILERO_MODEL_PATH` env var overrides for air-gapped deployments.
- No sha256 check (MIT model, pulled once, low risk).

### ONNX I/O (Silero v5 standard)
```
Inputs:
  input: float32[1, 512]       (audio frame, 16 kHz)
  sr:    int64 scalar          (16000)
  state: float32[2, 1, 128]    (combined h+c LSTM state)

Outputs:
  output: float32[1, 1]        (probability of speech)
  stateN: float32[2, 1, 128]   (new state — feed back next call)
```

### State machine (inside `rpi_audio_bridge.py`, uses `SileroStream`)

| Constant | Value | Meaning |
|---|---|---|
| `SPEECH_THRESHOLD` | `0.5` | Silero default |
| `ONSET_FRAMES` | `2` | ~64 ms of speech to trigger `speech_start` |
| `OFFSET_FRAMES` | `25` | ~800 ms of silence to trigger `speech_end` |
| `MIN_UTTERANCE_FRAMES` | `3` | ~96 ms — discard blips |

States: `IDLE → SPEAKING → IDLE`. Transitions emit the WS messages below.

---

## 4. Wire Protocol

Existing WS messages are preserved. Two new JSON control messages:

| Direction | Type | Payload | Meaning |
|---|---|---|---|
| Pi → PC | binary (existing) | ulaw 20 ms frame | Only sent while `SPEAKING` |
| Pi → PC | JSON (new) | `{"type":"speech_start"}` | VAD onset |
| Pi → PC | JSON (new) | `{"type":"speech_end"}` | VAD offset |
| Pi → PC | JSON (existing) | `call_start`, `call_end` | Unchanged |
| PC → Pi | binary (existing) | ulaw TTS response | Unchanged |
| PC → Pi | JSON (existing) | `{"type":"hangup"}` | Unchanged |

Binary ulaw **outside** a speech bracket is never sent. The PC's STT therefore sees continuous speech-only segments.

---

## 5. PC-Side Changes (`ai_server.py`)

### Remove
- `_STTBase._init_vad()`, `_STTBase.vad()` methods (entire RMS VAD).
- Constants: `SILENCE_THRESHOLD`, `SILENCE_FRAMES`, `MIN_SPEECH_BYTES`.

### Add / change
- `_STTBase` now holds `_buffer = bytearray()` and exposes `_transcribe()` only.
- WS message handlers in the server loop:
  - On `speech_start` → `_buffer.clear()`.
  - On binary ulaw frame → `ulaw2lin` + `ratecv` 8 k → 16 k → append to `_buffer`.
  - On `speech_end` → if `len(_buffer)` ≥ `3200` bytes (~100 ms of 16-bit PCM @ 16 kHz), call `_transcribe(bytes(_buffer))`; then clear.
- `WhisperSTT._transcribe`: `vad_filter=True` → `vad_filter=False`. Drop `vad_parameters`.
- `providers/stt_whisper.py` (standalone file): same flip, and remove the RMS silence-detection block since the only caller will be speech-only segments.

### Unchanged
- Deepgram `endpointing=300ms` stays — it's the provider's **own** utterance endpointing, orthogonal to VAD gating.
- OpenAI Realtime `server_vad` stays — same reason.
- LLM / TTS paths unchanged.

---

## 6. Dependencies

### RPi
Add to `32GSMgatewayServer/tests/ari_test/requirements_test.txt`:
```
onnxruntime>=1.17    # CPU ARM wheels available for Pi4/5, Python 3.9+
numpy>=1.24          # may already be pulled in transitively
```

### PC
No package changes. Only flag flips on existing faster-whisper call.

---

## 7. Call Lifecycle

- `call_start` → Pi constructs a fresh `SileroStream` (resets LSTM state). State machine starts `IDLE`.
- During call → frames classified, bracketed, forwarded.
- `call_end` → Pi drops the `SileroStream`. If mid-utterance, emit `speech_end` before `call_end` so the PC flushes its buffer cleanly.

---

## 8. Testing

1. **Unit (Pi)** — feed a known WAV with alternating speech/silence into `SileroStream`; assert `prob > 0.8` on speech frames and `prob < 0.2` on silence frames.
2. **Integration (Pi)** — replay a recorded ulaw call via RTP loopback into `rpi_audio_bridge.py`; inspect WS messages and verify `speech_start` / `speech_end` timing matches the audio visually.
3. **End-to-end** — run `test_03_ai_call.py` on a real call; confirm STT transcripts are equivalent to the current pipeline (no quality regression). Measure first-speech-to-STT latency.
4. **Perf** — log Silero inference time per frame on the Pi; target `< 10 ms` per 32 ms frame. Investigate if exceeded.

---

## 9. Out of Scope

- Barge-in handling.
- DTMF handling.
- Deepgram / OpenAI Realtime server-side VAD tuning.
- Per-frame VAD probability streaming to PC (rejected as Approach A3 during brainstorm).
- Full utterance buffering on Pi with a single binary blob send (rejected as A1 — would break streaming STT).
