#!/usr/bin/env python3
"""
Phase 3/4 — AI Call Test
Full pipeline: ARI + ExternalMedia + AI providers.

Usage:
    # STS mode (Gemini Live end-to-end):
    python3 test_03_ai_call.py --endpoint "Local/s@stasis-test"

    # Real GSM call with STS:
    python3 test_03_ai_call.py --endpoint "PJSIP/9876543210@1001"

    # STT → LLM → TTS mode:
    python3 test_03_ai_call.py --endpoint "PJSIP/9876543210@1001" --config config_stt_llm_tts.yaml
"""

import argparse
import asyncio
import logging
import sys
import threading

import yaml

from ari_handler import ARIHandler
from rtp_handler import RTPProtocol
from pipeline import build_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ai-call")


async def main():
    parser = argparse.ArgumentParser(description="AI Call Test")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--endpoint", help="Override endpoint (e.g. PJSIP/NUM@1001)")
    args = parser.parse_args()

    # Load config
    with open(args.config) as f:
        config = yaml.safe_load(f)

    endpoint = args.endpoint or config.get("endpoint", "Local/s@stasis-test")

    # --- 1. Start RTP UDP server ---
    rtp_cfg = config.get("rtp", {})
    rtp_host = rtp_cfg.get("listen_host", "127.0.0.1")
    rtp_port = rtp_cfg.get("listen_port", 20000)

    loop = asyncio.get_event_loop()
    transport, rtp_protocol = await loop.create_datagram_endpoint(
        RTPProtocol,
        local_addr=(rtp_host, rtp_port),
    )
    log.info("RTP server listening on %s:%s", rtp_host, rtp_port)

    # --- 2. Build AI pipeline ---
    pipeline = build_pipeline(config, rtp_protocol)
    system_prompt = config.get("llm", config.get("sts", {})).get(
        "system_prompt", "You are a helpful voice assistant.")

    # --- 3. Start ARI handler ---
    ari = ARIHandler(config)

    call_active = asyncio.Event()
    pipeline_task = None

    async def on_call_start(channel_id):
        nonlocal pipeline_task
        log.info("Call started — initializing AI pipeline")
        # Wait for first RTP packet (ExternalMedia connected)
        got_rtp = await rtp_protocol.wait_for_first_packet(timeout=15)
        if not got_rtp:
            log.error("No RTP packets received — ExternalMedia may have failed")
            return
        log.info("RTP flowing — starting AI pipeline")
        await pipeline.start(system_prompt)
        pipeline_task = asyncio.create_task(pipeline.run())
        call_active.set()

    async def on_call_end(channel_id):
        log.info("Call ended — stopping pipeline")
        await pipeline.stop()
        if pipeline_task:
            pipeline_task.cancel()
            try:
                await pipeline_task
            except asyncio.CancelledError:
                pass
        call_active.clear()
        # Print stats
        log.info("RTP packets in: %d, out: %d",
                 rtp_protocol.packets_received, rtp_protocol.packets_sent)
        # Stop the event loop
        loop.call_soon_threadsafe(loop.stop)

    async def on_dtmf(digit):
        log.info("DTMF pressed: %s", digit)
        if digit == "#":
            log.info("# pressed — hanging up")
            ari.hangup_caller()

    ari.on_call_start = on_call_start
    ari.on_call_end = on_call_end
    ari.on_dtmf = on_dtmf

    # --- 4. Start ARI WebSocket in background thread ---
    ws_thread = threading.Thread(
        target=ari.run_ws, args=(loop,), daemon=True)
    ws_thread.start()

    # Wait for WS connection
    connected = await ari.wait_connected(timeout=10)
    if not connected:
        log.error("Failed to connect ARI WebSocket")
        transport.close()
        return

    # --- 5. Originate the call ---
    log.info("Originating call to: %s", endpoint)
    result = ari.originate(endpoint)
    if not result:
        log.error("Originate failed")
        transport.close()
        return

    log.info("Call originated — waiting for answer...")
    log.info("Press Ctrl+C to hang up")

    # --- 6. Wait for call to complete ---
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        log.info("Interrupted — cleaning up")
        await pipeline.stop()
        ari.hangup_caller()
        ari.cleanup()
    finally:
        transport.close()
        log.info("Done")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
