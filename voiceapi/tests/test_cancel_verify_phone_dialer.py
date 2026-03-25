#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
from zoneinfo import ZoneInfo  # Python 3.9+
import jwt
import requests
import sys

# Path to the RS-256 private key used for SabkiApp service auth
PRIVATE_KEY = pathlib.Path("voiceapi/dev_keys/sabkiapp_voip_private.pem").read_text()

IST = ZoneInfo("Asia/Kolkata")

def make_token(seconds: int = 5) -> str:
    exp = dt.datetime.now(IST) + dt.timedelta(seconds=seconds)
    payload = {
        "iss": "sabkiapp_voip",
        "aud": "sabkiapp",
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")

if __name__ == "__main__":
    # Allow passing ref_no as first CLI arg; default for quick tests
    ref_no = sys.argv[1] if len(sys.argv) > 1 else "abc"

    token = make_token()
    url = "http://localhost:8100/cancel_ref_no"  # endpoint you provided
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    body = {
        "ref_no": ref_no
    }

    print("→ POST", url)
    print("→ Body:", json.dumps(body, indent=2))
    try:
        r = requests.post(url, json=body, headers=headers, timeout=10)
        print("←", r.status_code)
        try:
            print(json.dumps(r.json(), indent=2))
        except Exception:
            print(r.text)
    except requests.RequestException as e:
        print("Request failed:", e)
