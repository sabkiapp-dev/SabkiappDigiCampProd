#!/bin/bash
# Launcher for RPi: sets SILERO_MODEL_PATH (pi home not writable) and runs bridge
export SILERO_MODEL_PATH="$(dirname "$(readlink -f "$0")")/models/silero_vad_v5.onnx"
export PYTHONUNBUFFERED=1
cd "$(dirname "$(readlink -f "$0")")"
exec python3 -u rpi_audio_bridge.py "$@"
