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
import time
from pathlib import Path
from typing import Optional, Set

log = logging.getLogger(__name__)

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
        # Flip the flag; _wait_stop polls it and exits cleanly, which
        # unwinds the `async with serve(...)` without tearing the loop.
        self._stop.set()

    # ── server ──
    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as e:
            log.error(f"Dashboard server crashed: {e}")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _serve(self) -> None:
        import websockets

        async def handler(ws):
            # websockets >=10: handler(ws); path is on ws.path or ws.request.path
            self._clients.add(ws)
            try:
                hello = dict(self._hello)
                hello["t"] = _now_ms()
                await ws.send(json.dumps(hello))
                async for _ in ws:
                    pass
            finally:
                self._clients.discard(ws)

        # websockets 12+ uses (connection, request); older uses (path, headers).
        # Try both — newer first.
        async def process_request_new(connection, request):
            return await self._serve_static_new(request.path)

        async def process_request_legacy(path, request_headers):
            return await self._serve_static_legacy(path)

        serve = websockets.serve

        last_err = None
        for pr in (process_request_new, process_request_legacy, None):
            try:
                kwargs = {"process_request": pr} if pr is not None else {}
                async with serve(handler, self._host, self._port, **kwargs):
                    log.info(f"[DASH] Listening on http://{self._host}:{self._port}/")
                    print(f"[DASH] Listening on http://{self._host}:{self._port}/",
                          flush=True)
                    await asyncio.gather(self._broadcaster(), self._wait_stop())
                return
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"Could not start websockets server: {last_err}")

    async def _wait_stop(self):
        while not self._stop.is_set():
            await asyncio.sleep(0.25)

    async def _broadcaster(self):
        """Drain the thread-safe queue and fan-out to WS clients."""
        loop = asyncio.get_event_loop()
        while not self._stop.is_set():
            try:
                event = await loop.run_in_executor(
                    None, self._queue_get_blocking)
            except Exception:
                continue
            if event is None:
                continue
            try:
                msg = json.dumps(event)
            except Exception as e:
                log.warning(f"[DASH] skip non-serializable event: {e}")
                continue
            dead = []
            for ws in list(self._clients):
                try:
                    await ws.send(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._clients.discard(ws)

    def _queue_get_blocking(self):
        """Blocking get with a timeout so we periodically check _stop."""
        try:
            return self._queue.get(timeout=0.25)
        except queue.Empty:
            return None

    async def _serve_static_new(self, path: str):
        """websockets 12+ process_request — return a Response or None."""
        from websockets.http11 import Response
        data = self._dispatch_static(path)
        if data is None:
            return None
        status, content_type, body = data
        return Response(status, b"OK" if status == 200 else b"Not Found",
                        [("Content-Type", content_type),
                         ("Cache-Control", "no-store")], body)

    async def _serve_static_legacy(self, path: str):
        """Older websockets — return (status, headers, body) tuple or None."""
        data = self._dispatch_static(path)
        if data is None:
            return None
        status, content_type, body = data
        return (status, [("Content-Type", content_type),
                         ("Cache-Control", "no-store")], body)

    def _dispatch_static(self, path: str):
        """Return (status, content_type, body_bytes) for static paths; None for WS."""
        path = path.split("?", 1)[0]
        if path == "/stream":
            return None
        if path in ("/", "/index.html"):
            return _read_file(self._static_dir / "index.html",
                              "text/html; charset=utf-8")
        if path == "/app.js":
            return _read_file(self._static_dir / "app.js",
                              "application/javascript; charset=utf-8")
        return (404, "text/plain", b"not found")


def _read_file(path: Path, content_type: str):
    try:
        return (200, content_type, path.read_bytes())
    except FileNotFoundError:
        return (500, "text/plain", f"missing: {path}".encode())


def _now_ms() -> float:
    return time.monotonic() * 1000.0
