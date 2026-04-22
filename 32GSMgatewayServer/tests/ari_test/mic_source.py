"""USB mic capture via `sox` subprocess — emits 512-sample float32 frames @ 16 kHz.

Used for VAD calibration on RPi without an active phone call. Feeds directly
into VADGate.feed_pcm16_frame() — no ulaw, no resampling.
"""
from __future__ import annotations

import logging
import subprocess
import threading
from typing import Callable, Optional

import numpy as np

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512
BYTES_PER_FRAME = FRAME_SAMPLES * 2  # int16 mono


class MicSource:
    """Wraps `sox` reading raw PCM16 from an ALSA device.

    on_frame(frame: np.ndarray[float32, (512,)]) is called for each captured
    frame. Callback runs on the reader thread — keep it quick and non-blocking.
    """

    def __init__(
        self,
        device: str = "plughw:2,0",
        on_frame: Optional[Callable[[np.ndarray], None]] = None,
    ):
        self.device = device
        self.on_frame = on_frame
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running():
            return
        self._stop.clear()
        cmd = [
            "sox", "-q", "-t", "alsa", self.device,
            "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16",
            "-e", "signed-integer", "-t", "raw", "-",
        ]
        log.info(f"[MIC] starting: {' '.join(cmd)}")
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._thread = threading.Thread(target=self._run, name="mic-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
            except Exception:
                pass
            self._proc = None
        self._thread = None

    def _run(self) -> None:
        assert self._proc is not None
        stdout = self._proc.stdout
        try:
            while not self._stop.is_set():
                data = stdout.read(BYTES_PER_FRAME)
                if not data or len(data) < BYTES_PER_FRAME:
                    log.warning(f"[MIC] short read ({len(data) if data else 0}B) — ending")
                    break
                samples = (np.frombuffer(data, dtype=np.int16)
                             .astype(np.float32) / 32768.0)
                if self.on_frame is not None:
                    try:
                        self.on_frame(samples)
                    except Exception as e:
                        log.warning(f"[MIC] on_frame error: {e}")
        finally:
            log.info("[MIC] reader thread exiting")
