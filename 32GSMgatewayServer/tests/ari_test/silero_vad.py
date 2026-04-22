"""Silero VAD v5 — runs on RPi. Gates ulaw audio so only speech crosses WS."""
from __future__ import annotations

import os
import urllib.request
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "silero"
LOCAL_MODELS_DIR = Path(__file__).parent / "models"
MODEL_URL = "https://huggingface.co/runanywhere/silero-vad-v5/resolve/main/silero_vad.onnx"
MODEL_FILENAME = "silero_vad_v5.onnx"


def model_path() -> str:
    """Return path to Silero v5 ONNX. Resolution order:
      1. $SILERO_MODEL_PATH (explicit override)
      2. ./models/silero_vad_v5.onnx next to this file (checked-in / pre-deployed)
      3. ~/.cache/silero/silero_vad_v5.onnx (download once if missing)
    """
    env = os.environ.get("SILERO_MODEL_PATH")
    if env:
        return env

    local = LOCAL_MODELS_DIR / MODEL_FILENAME
    if local.exists():
        return str(local)

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

SPEECH_THRESHOLD = 0.2         # Silero prob cutoff (0–1)
AMPLITUDE_THRESHOLD = 0.084    # max-abs amplitude floor (0–1). 0 = disabled.
AMPLITUDE_HOLD_FRAMES = 10     # once amp crosses threshold, gate stays open for N frames.
                               # Fills short quiet gaps in otherwise-loud speech.
ONSET_FRAMES = 2               # ~64 ms of speech to trigger speech_start
OFFSET_FRAMES = 10             # ~320 ms of silence to trigger speech_end
MIN_UTTERANCE_FRAMES = 3       # ~96 ms — discard blips
PRE_ROLL_FRAMES = 5            # leading frames to prepend on is-speech rising edge
LSTM_RESET_SILENCE_FRAMES = 60 # reset Silero LSTM after this many silent frames
                               # (~2 s). Prevents state drift that causes short
                               # post-silence words (ok/hmm/haan) to be missed.

STATE_IDLE = "idle"
STATE_SPEAKING = "speaking"


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
        # Pending ulaw buffered during ONSET_FRAMES window — flushed on speech_start
        self._pending_ulaw = bytearray()
        self._frame_count = 0
        self._utterance_start_t = 0.0
        self._last_utterance_ms = 0.0
        self._amp_hold_counter = 0  # frames remaining with amp gate held open
        self._utt_pcm_buf = bytearray()      # filtered PCM16 — only is-speech frames
        self._utt_pcm_buf_raw = bytearray()  # raw PCM16 — every frame while SPEAKING
        self._last_utterance_pcm = b""       # filtered, captured on speech_end
        self._last_utterance_pcm_raw = b""   # raw, captured on speech_end
        self._flushed_preroll = False        # one-shot flag per utterance
        self._consec_quiet = 0               # frames of consecutive low-prob silence
        # Sticky is-speech flag (mirrors the dashboard viz state machine):
        #   0 → 1: need BOTH prob AND amp above threshold
        #   1 → 0: prob drops below threshold
        self._viz_is_speech = False
        # Rolling buffer of the last N PCM16 frames so we can prepend a few
        # frames of leading context when the viz flag flips on (prevents the
        # first syllable of a word from being clipped off the echo).
        # Buffer size is driven by the module-level PRE_ROLL_FRAMES so it can
        # be tuned at runtime from the dashboard.
        self._pre_roll = []                 # list[bytes], each = one 512-sample frame

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
        self._amp_hold_counter = 0
        self._utt_pcm_buf.clear()
        self._utt_pcm_buf_raw.clear()
        self._last_utterance_pcm = b""
        self._last_utterance_pcm_raw = b""
        self._viz_is_speech = False
        self._pre_roll.clear()
        self._flushed_preroll = False
        self._consec_quiet = 0

    def is_speaking(self) -> bool:
        return self._state == STATE_SPEAKING

    def last_utterance_ms(self) -> float:
        """Duration of the most recent completed utterance in milliseconds.
        Zero if no utterance has completed yet."""
        return self._last_utterance_ms

    def last_utterance_pcm(self) -> bytes:
        """VAD-filtered PCM16 @ 16 kHz of the most recent completed utterance
        (only frames where is-speech flag was 1, with pre-roll)."""
        return self._last_utterance_pcm

    def last_utterance_pcm_raw(self) -> bytes:
        """Unfiltered PCM16 @ 16 kHz of the most recent completed utterance —
        every frame captured while the state machine was SPEAKING, including
        silences inside the hysteresis window. Useful to hear what the VAD
        would have sent without the is-speech filter."""
        return self._last_utterance_pcm_raw

    def feed(self, ulaw_chunk: bytes):
        """Feed raw ulaw bytes from RTP. Drives the VAD pipeline and callbacks."""
        for frame in self._frames.feed(ulaw_chunk):
            self._on_frame(frame, ulaw_chunk)

    def feed_pcm16_frame(self, frame: np.ndarray):
        """Feed a pre-resampled 512-sample float32 PCM frame @ 16 kHz.

        Used by alternate audio sources (e.g. USB mic) that bypass the
        ulaw → PCM16 resample step. State machine runs normally but
        on_speech_audio is NOT invoked (there is no ulaw to forward)."""
        self._on_frame(frame, b"", suppress_audio=True)

    def _on_frame(self, frame, ulaw_chunk: bytes, suppress_audio: bool = False):
        import time as _time

        self._frame_count += 1
        t0 = _time.monotonic()
        prob = self._stream.process(frame)
        latency_ms = (_time.monotonic() - t0) * 1000.0
        frame_max_abs = float(np.abs(frame).max())
        # Sticky amp gate: a single loud frame holds the gate open for
        # AMPLITUDE_HOLD_FRAMES subsequent frames. Fills short quiet gaps
        # (like consonant stops) inside an otherwise-loud utterance.
        if frame_max_abs >= AMPLITUDE_THRESHOLD:
            self._amp_hold_counter = AMPLITUDE_HOLD_FRAMES
        elif self._amp_hold_counter > 0:
            self._amp_hold_counter -= 1
        amp_pass = self._amp_hold_counter > 0 or AMPLITUDE_THRESHOLD == 0.0
        prob_pass = prob >= SPEECH_THRESHOLD

        # LSTM drift guard: after a long quiet stretch Silero's internal state
        # gets stuck near a "silence attractor" and stops responding cleanly
        # to short post-silence words. Reset the stream when we're idle and
        # have seen LSTM_RESET_SILENCE_FRAMES quiet frames in a row.
        if self._state == STATE_IDLE and not prob_pass:
            self._consec_quiet += 1
            if (LSTM_RESET_SILENCE_FRAMES > 0
                    and self._consec_quiet == LSTM_RESET_SILENCE_FRAMES):
                self._stream.reset()
        else:
            self._consec_quiet = 0
        # Asymmetric gate:
        #   onset — strict: only Silero prob starts a new utterance (amp alone
        #   on ambient noise must not trigger speech).
        #   continuation — lenient: either prob OR amp keeps us in speech, so
        #   a short prob dip during a loud word doesn't close the utterance.
        # Speech ends only when BOTH prob and amp have dropped.
        if self._state == STATE_IDLE:
            is_speech = prob_pass
        else:
            is_speech = prob_pass or amp_pass

        # Pre-compute the PCM16 bytes for this frame so we can push to the
        # rolling pre-roll buffer and optionally to the utterance buffer.
        pcm16 = (frame * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()

        # Update sticky is-speech viz flag (mirror of dashboard logic):
        #   0 → 1: need BOTH prob AND amp above
        #   1 → 0: prob drops below
        prev_viz = self._viz_is_speech
        if not self._viz_is_speech:
            if prob_pass and amp_pass:
                self._viz_is_speech = True
        else:
            if not prob_pass:
                self._viz_is_speech = False

        # Filtered buffer: we only accumulate while BOTH state machine is
        # SPEAKING and the is-speech viz flag is 1. The first time that
        # happens, flush the pre-roll so the first syllable isn't clipped.
        # Flag is one-shot per utterance (cleared on offset / reset).
        if self._state == STATE_SPEAKING and self._viz_is_speech:
            if not self._flushed_preroll:
                for pre in self._pre_roll:
                    self._utt_pcm_buf.extend(pre)
                self._flushed_preroll = True
            self._utt_pcm_buf.extend(pcm16)

        # Raw buffer — every frame while SPEAKING, no filter.
        # Also prepend pre-roll on the first SPEAKING frame.
        if self._state == STATE_SPEAKING:
            if len(self._utt_pcm_buf_raw) == 0 and self._pre_roll:
                for pre in self._pre_roll:
                    self._utt_pcm_buf_raw.extend(pre)
            self._utt_pcm_buf_raw.extend(pcm16)

        # Maintain the rolling pre-roll buffer (bounded, drops oldest).
        self._pre_roll.append(pcm16)
        while len(self._pre_roll) > PRE_ROLL_FRAMES:
            self._pre_roll.pop(0)

        if self._state == STATE_IDLE:
            # Keep a small rolling buffer so the first audio after speech_start isn't lost
            if not suppress_audio:
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
                    self._utterance_start_t = _time.monotonic()
                    self._on_start()
                    if self._pending_ulaw and not suppress_audio:
                        self._on_audio(bytes(self._pending_ulaw))
                        self._pending_ulaw.clear()
            else:
                self._consec_speech = 0
        else:  # STATE_SPEAKING
            if not suppress_audio:
                self._on_audio(ulaw_chunk)
            self._speech_frame_count += 1
            if is_speech:
                self._consec_silence = 0
            else:
                self._consec_silence += 1
                if self._consec_silence >= OFFSET_FRAMES:
                    emitted_end = self._speech_frame_count >= MIN_UTTERANCE_FRAMES
                    self._last_utterance_ms = (_time.monotonic() - self._utterance_start_t) * 1000.0
                    # Snapshot both buffers (filtered + raw) for the bridge.
                    self._last_utterance_pcm = bytes(self._utt_pcm_buf) if emitted_end else b""
                    self._last_utterance_pcm_raw = bytes(self._utt_pcm_buf_raw) if emitted_end else b""
                    self._utt_pcm_buf.clear()
                    self._utt_pcm_buf_raw.clear()
                    self._flushed_preroll = False
                    self._state = STATE_IDLE
                    self._consec_speech = 0
                    self._consec_silence = 0
                    self._speech_frame_count = 0
                    self._pending_ulaw.clear()
                    if emitted_end:
                        self._on_end()

        if self._on_metrics is not None:
            max_abs = frame_max_abs
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
                pass
