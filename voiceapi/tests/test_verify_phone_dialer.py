#!/usr/bin/env python3
import datetime as dt
from zoneinfo import ZoneInfo  # Python 3.9+
import pathlib, jwt, requests

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

token   = make_token()
# url     = "https://asterisk.sabkiapp.com/verify_add_to_phone_dialer"
url     = "http://localhost:8100/verify_add_to_phone_dialer"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type":  "application/json",
}
body = {
    "ref_no":        "bxade333dadesaec",
    "name":          "Gopal Kumar",
    "phone_number":  "9934445076",
    "channel_name":  "Bharatiya Parivar",
    "surveyor_name": "Gaurav",
    "language":      "en",
}

print("→ POST", url)
r = requests.post(url, json=body, headers=headers, timeout=10)
print("←", r.status_code, r.text)
