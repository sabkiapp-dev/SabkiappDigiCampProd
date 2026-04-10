#!/usr/bin/env python3
"""
Standalone smoke-test.
Adjust ENDPOINT / API_KEY / PAYLOAD as needed and run:

    python tests/test_push_call_status.py
"""

from __future__ import annotations

import os
import sys
import pathlib
import datetime as dt
import uuid

import pytz
import django
import requests

# ── Bootstrap Django just like manage.py ───────────────────────────
# "…/VoiceAPI/voiceapi" is the folder that contains manage.py *and*
# the actual Django package (voiceapi/__init__.py, settings.py, …).
MANAGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "voiceapi"
sys.path.insert(0, str(MANAGE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "voiceapi.settings")
django.setup()

# ── now the import works ───how ────────────────────────────────────────────────
from api.call_status_pusher import CallStatusPusher   # noqa: E402


IST = pytz.timezone("Asia/Kolkata")

PAYLOAD = {
    # "ref_no":      f"UNITTEST-{uuid.uuid4().hex[:8]}",
    "ref_no": "eyJpIjoyNywicCI6MywicyI6MX0:1uV6vQ:Tx5JszUPble041LdrPxmLWF_iOg7kQDAu182w3BCVOg",
    "status":      "accepted",        # pending | not_answered | no_dtmf | rejected | accepted
    "retry_count": 1,
    "retry_at":    dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
}

success = CallStatusPusher.push(PAYLOAD)
print("success =", success)
sys.exit(0 if success else 1)
