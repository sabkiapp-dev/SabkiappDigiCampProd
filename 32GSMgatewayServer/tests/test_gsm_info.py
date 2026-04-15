#!/usr/bin/env python3
import requests
import json

BASE = "http://localhost:9000"   # adjust if your dev server runs elsewhere

url = f"{BASE}/gsm-info"
try:
    print(f"Making request to: {url}")
    resp = requests.get(url, timeout=10)
    print(f"Response status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Response text: {resp.text}")
    resp.raise_for_status()
    data = resp.json()
    print("Response JSON:", json.dumps(data, indent=2))
except requests.RequestException as e:
    print("Error calling gsm-info endpoint:", str(e))
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response status: {e.response.status_code}")
        print(f"Response text: {e.response.text}")
