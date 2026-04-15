#!/usr/bin/env python3
"""
Integration test for the /authenticate endpoint.

Usage:
    1. Generate keys:  python tools/generate_ed25519_keys.py
    2. Start gateway:  cd 32GSMgatewayServer/gateway && python manage.py runserver 0.0.0.0:9000
    3. Run tests:      python 32GSMgatewayServer/tests/test_authenticate.py
"""

import datetime
import json
import sys
from pathlib import Path

import jwt
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
PRIVATE_KEY = (ROOT / "DigiCampServer" / "digicamp" / "dev_keys" / "host_ed25519_private.pem").read_text()

ISSUER = "digicamp"
AUDIENCE = "gateway"
BASE_URL = "http://localhost:9000"


def make_token(host_id="host1", ttl_seconds=60):
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "iat": now,
         "exp": now + datetime.timedelta(seconds=ttl_seconds),
         "host_id": host_id},
        PRIVATE_KEY, algorithm="EdDSA",
    )


def test(name, resp, expect_status, expect_auth):
    ok = resp.status_code == expect_status and resp.json().get("authenticated") is expect_auth
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}  (status={resp.status_code}, body={resp.json()})")
    if not ok:
        sys.exit(1)


def main():
    print("Testing /authenticate endpoint...\n")

    # 1. Valid token
    r = requests.post(f"{BASE_URL}/authenticate",
                      headers={"Authorization": f"Bearer {make_token()}"}, timeout=10)
    test("Valid token", r, 200, True)

    # 2. Expired token
    r = requests.post(f"{BASE_URL}/authenticate",
                      headers={"Authorization": f"Bearer {make_token(ttl_seconds=-1)}"}, timeout=10)
    test("Expired token", r, 401, False)

    # 3. No header
    r = requests.post(f"{BASE_URL}/authenticate", timeout=10)
    test("No auth header", r, 401, False)

    # 4. Garbage token
    r = requests.post(f"{BASE_URL}/authenticate",
                      headers={"Authorization": "Bearer not.a.real.token"}, timeout=10)
    test("Garbage token", r, 401, False)

    print("\nAll tests passed!")


if __name__ == "__main__":
    main()
