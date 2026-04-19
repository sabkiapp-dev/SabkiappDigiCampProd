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
            pass

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
        # Server loop — filled in by Task 5.
        pass
