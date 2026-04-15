"""Lightweight helper to send a call-status payload to SabkiApp’s
<verify-family-member> endpoint.  Both CallStatusPusher and the
retry handler import this so the HTTP-request logic lives in one place.
"""
from __future__ import annotations

import os, json, jwt, datetime as dt, requests
from zoneinfo import ZoneInfo
from typing import Tuple

from django.conf import settings
from .models.users import Users

__all__ = ["send_verify_status"]

TIMEOUT = 5  # seconds
ISS = "sabkiapp_voip"
AUD = "sabkiapp"

# ------------------------------------------------------------------
# Helper: build a short-lived JWT each call
# ------------------------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")

def _make_jwt(seconds: int = 500) -> str:
    exp = dt.datetime.now(IST) + dt.timedelta(seconds=seconds)
    payload = {"iss": ISS, "aud": AUD, "exp": int(exp.timestamp())}
    token = jwt.encode(payload, settings.SABKIAPP_VOIP_PRIVATE_KEY, algorithm="RS256")
    print("token ::", token)
    print("payload ::", payload)
    return token


def _get_api_key() -> str:
    """Fetch the API key from the configured service user each call."""
    SERVICE_USER_ID = getattr(settings, "SABKIAPP_SERVICE_USER_ID", 10006666)
    user = Users.objects.only("api_key").get(id=SERVICE_USER_ID)
    if not user.api_key:
        raise RuntimeError(
            f"Service user id={SERVICE_USER_ID} has no api_key value"
        )
    return user.api_key


def _endpoint() -> str:
    base = getattr(settings, "SABKIAPP_BASE_URL", "https://staging.sabkiapp.com")
    return f"{base.rstrip('/')}/survey/verify-family-member"


def send_verify_status(payload: dict) -> Tuple[bool, int | None, str | None]:
    """Return (success, resp_code, resp_body_trunc).

    Success is True if HTTP 200.
    With `settings.SABKIAPP_FAKE_HTTP = True` or env `SABKIAPP_FAKE_HTTP=1`
    the request is faked and the function returns (True, 200, "FAKE").
    """
    # -------- dry-run shortcut --------
    fake = (
        getattr(settings, "SABKIAPP_FAKE_HTTP", False)
        or os.getenv("SABKIAPP_FAKE_HTTP", "").lower() in {"1", "true", "yes"}
    )
    if fake:
        print(f"• [FAKE] Would POST to {_endpoint()}:\n{json.dumps(payload, indent=2, default=str)}")
        return True, 200, "FAKE"

    jwt_token = _make_jwt()
    try:
        resp = requests.post(
            _endpoint(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {jwt_token}",
            },
            json=payload,
            timeout=TIMEOUT,
        )
        print("resp ::", resp.json())
    except Exception as exc:
        return False, None, str(exc)

    if resp.status_code == 200:
        return True, 200, resp.text[:2048]
    return False, resp.status_code, resp.text[:2048]
