"""
CallStatusPusher
================
Send call-status JSON to SabkiApp’s <verify-family-member> endpoint.
Rules
-----

1.  If *ErrorVerifyPhoneDialer* already contains rows
    • Skip the HTTP call.  
    • Log the payload to the error table.  
    • Sleep 10 s, then run `process_retry_queue()` in the same thread.

2.  If the table is empty
    • Fetch the API key from the service user (id = settings.SABKIAPP_SERVICE_USER_ID
      or 10006666 by default).  
        – On any failure to obtain the key → log the payload and exit.  
    • Perform the HTTP POST.  
        – HTTP 200 → success.  
        – Any other status / exception → log the payload (no immediate retry).
"""

from __future__ import annotations

import datetime as dt
import time
import typing as _t
import json
import pytz

from .sabkiapp_client import send_verify_status
import requests
from django.conf import settings
from django.db import transaction

from .models.error_verify_phone_dialer import ErrorVerifyPhoneDialer
from .models.users import Users
 
__all__ = ["CallStatusPusher"]


class CallStatusPusher:
    """Stateless helper – use classmethods only."""

    # TIMEOUT removed – handled by sabkiapp_client

    # ------------------------------------------------------------------
    # API-key helper (no caching)
    # ------------------------------------------------------------------
    @classmethod
    def _get_api_key(cls) -> str:
        """Fetch the API key from the configured service user each call."""
        SERVICE_USER_ID = getattr(settings, "SABKIAPP_SERVICE_USER_ID", 10006666)

        try:
            user = Users.objects.only("api_key").get(id=SERVICE_USER_ID)
        except Users.DoesNotExist as exc:
            raise RuntimeError(
                f"Service user id={SERVICE_USER_ID} not found"
            ) from exc

        if not user.api_key:
            raise RuntimeError(
                f"Service user id={SERVICE_USER_ID} has no api_key value"
            )

        return user.api_key

    # ------------------------------------------------------------------
    # Endpoint helper
    # ------------------------------------------------------------------
    @classmethod
    def _endpoint(cls) -> str:
        base = getattr(settings, "SABKIAPP_BASE_URL", "https://staging.sabkiapp.com")
        return f"{base.rstrip('/')}/survey/verify-family-member"

    # ------------------------------------------------------------------
    # Public entry-point
    # ------------------------------------------------------------------
    @classmethod
    def push(cls, payload: dict) -> bool:
        """Return True if delivered with HTTP 200, else False (queued)."""
        payload = dict(payload)  # don’t mutate caller
        if "ref_no" not in payload or "status" not in payload:
            raise ValueError("payload must include 'ref_no' and 'status'")
        payload.setdefault("retry_count", 0)

        # Case A – pending errors already exist
        if cls._has_pending_errors():
            print("• Pending errors detected – queueing payload")
            cls._log_failure(payload, None, "Queued – pending errors")
            cls._sleep_then_process_retry(1)
            return False

        # Case B – table empty → attempt HTTP call via shared client
        print("• Payload being sent:")
        print(json.dumps(payload, indent=2, default=str))

        success, code, body = send_verify_status(payload)
        if success:
            print(f"✓ Delivered (HTTP 200) for {payload['ref_no']}")
            return True

        print(f"× HTTP {code if code else 'ERR'} – queued for retry")
        cls._log_failure(payload, code, body)
        return False

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _ist_now_naive() -> dt.datetime:
        return dt.datetime.now(pytz.timezone("Asia/Kolkata")).replace(tzinfo=None)

    @classmethod
    def _has_pending_errors(cls) -> bool:
        return ErrorVerifyPhoneDialer.objects.exists()

    # ------------------------------------------------------------------
    # Error logging  (verify_datetime removed)
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def _log_failure(
        cls,
        payload: dict,
        code: _t.Optional[int],
        body: _t.Optional[str],
    ) -> None:
        """Insert one row into ErrorVerifyPhoneDialer."""
        attempted_at = cls._ist_now_naive()
        if settings.USE_TZ:
            from django.utils import timezone

            if timezone.is_naive(attempted_at):
                attempted_at = timezone.make_aware(
                    attempted_at, timezone=pytz.timezone("Asia/Kolkata")
                )

        ErrorVerifyPhoneDialer.objects.create(
            ref_no=payload["ref_no"],
            trials=payload["retry_count"],
            status=payload["status"],
            attempted_at=attempted_at,
            response_code=code,
            response_body=body,
        )
        print(f"• Logged error for {payload['ref_no']}")

    # ------------------------------------------------------------------
    # Retry processing in the same thread
    # ------------------------------------------------------------------
    @classmethod
    def _sleep_then_process_retry(cls, delay_seconds: int = 1) -> None:
        print(f"• Sleeping {delay_seconds}s before processing retry queue …")
        time.sleep(delay_seconds)
        try:
            from .retry_error_handle import process_retry_queue
            process_retry_queue()
            print("• Retry queue processed")
        except Exception as exc:
            print(f"• Retry handler error: {exc}")
