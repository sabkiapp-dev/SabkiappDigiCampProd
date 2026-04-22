"""YAMNet audio event classifier — 521 AudioSet classes.

Runs on the dev PC (not RPi — tflite-runtime isn't available for Python 3.12
on the Pi at the time of writing). ai_server calls classify() alongside STT
on each detected utterance to attach category labels to the transcript.

Model: Google's canonical yamnet.tflite (~4 MB).
Input: float32 waveform at 16 kHz, exactly 15600 samples (~0.975 s).
Output: float32 [1, 521] — logits over AudioSet ontology.

For utterances longer than 0.975 s we slide the window and max-pool scores so
a brief "cough" in a longer clip still ranks high.
"""
from __future__ import annotations

import csv
import logging
import threading
from pathlib import Path
from typing import List, Tuple

import numpy as np

log = logging.getLogger(__name__)

HERE = Path(__file__).parent
MODEL_PATH = HERE / "models" / "yamnet.tflite"
CLASS_MAP_PATH = HERE / "models" / "yamnet_class_map.csv"
WINDOW_SAMPLES = 15600            # 0.975 s @ 16 kHz — fixed YAMNet input size
HOP_SAMPLES = 15600 // 2          # 50 % overlap for sliding classification


_labels: List[str] | None = None
_interp_lock = threading.Lock()
_interp = None


def _load_labels() -> List[str]:
    """Read yamnet_class_map.csv → list of 521 human-readable labels."""
    global _labels
    if _labels is not None:
        return _labels
    with open(CLASS_MAP_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        labels = [row["display_name"] for row in reader]
    if len(labels) != 521:
        log.warning(f"[YAMNET] expected 521 labels, got {len(labels)}")
    _labels = labels
    return labels


def _get_interp():
    """Lazy-load the tflite interpreter. Thread-safe."""
    global _interp
    if _interp is not None:
        return _interp
    with _interp_lock:
        if _interp is not None:
            return _interp
        from ai_edge_litert.interpreter import Interpreter
        interp = Interpreter(model_path=str(MODEL_PATH))
        interp.allocate_tensors()
        _interp = interp
        _load_labels()
        log.info(f"[YAMNET] loaded {MODEL_PATH.name}")
    return _interp


def classify(pcm16_16k: bytes, top_k: int = 3) -> List[Tuple[str, float]]:
    """Classify an utterance.

    pcm16_16k: bytes, mono int16 PCM @ 16 kHz.
    Returns top_k (label, score) pairs sorted by score descending. Silence or
    very short clips return an empty list.
    """
    if not pcm16_16k:
        return []
    samples = np.frombuffer(pcm16_16k, dtype=np.int16).astype(np.float32) / 32768.0
    if samples.size < 1600:   # < 0.1 s — skip, model needs real content
        return []

    interp = _get_interp()
    in_idx = interp.get_input_details()[0]["index"]
    out_idx = interp.get_output_details()[0]["index"]

    # Slide a 0.975 s window over the utterance with 50% overlap, max-pool
    # class scores so a short event (cough) in a longer clip still ranks high.
    max_scores = np.zeros(521, dtype=np.float32)
    n = samples.size
    if n < WINDOW_SAMPLES:
        # Pad short clips to window length so yamnet still runs.
        window = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
        window[:n] = samples
        with _interp_lock:
            interp.set_tensor(in_idx, window)
            interp.invoke()
            scores = interp.get_tensor(out_idx)[0]
        np.maximum(max_scores, scores, out=max_scores)
    else:
        start = 0
        while True:
            end = start + WINDOW_SAMPLES
            if end > n:
                start = max(0, n - WINDOW_SAMPLES)
                end = n
            window = samples[start:end]
            with _interp_lock:
                interp.set_tensor(in_idx, window)
                interp.invoke()
                scores = interp.get_tensor(out_idx)[0]
            np.maximum(max_scores, scores, out=max_scores)
            if end >= n:
                break
            start += HOP_SAMPLES

    labels = _load_labels()
    # Top-k indices by score
    top_idx = np.argsort(max_scores)[-top_k:][::-1]
    return [(labels[i], float(max_scores[i])) for i in top_idx]


def classify_pcm16_bytes_safe(pcm16_16k: bytes, top_k: int = 3) -> List[Tuple[str, float]]:
    """Wrapper that never raises — logs and returns empty list on error."""
    try:
        return classify(pcm16_16k, top_k=top_k)
    except Exception as e:
        log.warning(f"[YAMNET] classify failed: {e}")
        return []
