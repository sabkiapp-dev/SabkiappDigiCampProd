#!/usr/bin/env python3
"""
Phase 1 — ARI Ping Test
Verifies ARI HTTP is enabled and responding on Asterisk.

Usage:
    python3 test_01_ping.py
    python3 test_01_ping.py --host 192.168.8.59   # remote RPi
"""

import argparse
import json
import sys

import requests


def main():
    parser = argparse.ArgumentParser(description="ARI Ping Test")
    parser.add_argument("--host", default="localhost", help="Asterisk host")
    parser.add_argument("--port", default=8088, type=int, help="ARI HTTP port")
    parser.add_argument("--user", default="ari_user", help="ARI username")
    parser.add_argument("--password", default="ari_pass", help="ARI password")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}/ari"
    auth = (args.user, args.password)
    passed = 0
    failed = 0

    # --- Test 1: Asterisk info ---
    print("=" * 60)
    print("TEST 1: GET /ari/asterisk/info")
    print("=" * 60)
    try:
        resp = requests.get(f"{base}/asterisk/info", auth=auth, timeout=5)
        if resp.status_code == 200:
            info = resp.json()
            print(f"  Asterisk system name : {info.get('system', {}).get('entity_id', 'N/A')}")
            print(f"  Asterisk version     : {info.get('build', {}).get('os', 'N/A')}")
            print(f"  Status               : PASS")
            passed += 1
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            print(f"  Status               : FAIL")
            failed += 1
    except requests.ConnectionError:
        print(f"  Cannot connect to {base}")
        print(f"  Is Asterisk running? Is http.conf enabled?")
        print(f"  Status               : FAIL")
        failed += 1
    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Status               : FAIL")
        failed += 1

    # --- Test 2: List endpoints ---
    print()
    print("=" * 60)
    print("TEST 2: GET /ari/endpoints")
    print("=" * 60)
    try:
        resp = requests.get(f"{base}/endpoints", auth=auth, timeout=5)
        if resp.status_code == 200:
            endpoints = resp.json()
            pjsip_eps = [ep for ep in endpoints if ep.get("technology") == "PJSIP"]
            print(f"  Total endpoints      : {len(endpoints)}")
            print(f"  PJSIP endpoints      : {len(pjsip_eps)}")
            if pjsip_eps:
                names = sorted([ep.get("resource", "?") for ep in pjsip_eps])
                print(f"  PJSIP names          : {', '.join(names[:5])}{'...' if len(names) > 5 else ''}")
            print(f"  Status               : PASS")
            passed += 1
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            print(f"  Status               : FAIL")
            failed += 1
    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Status               : FAIL")
        failed += 1

    # --- Test 3: List channels (should be empty or show active calls) ---
    print()
    print("=" * 60)
    print("TEST 3: GET /ari/channels")
    print("=" * 60)
    try:
        resp = requests.get(f"{base}/channels", auth=auth, timeout=5)
        if resp.status_code == 200:
            channels = resp.json()
            print(f"  Active channels      : {len(channels)}")
            print(f"  Status               : PASS")
            passed += 1
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            print(f"  Status               : FAIL")
            failed += 1
    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Status               : FAIL")
        failed += 1

    # --- Test 4: List bridges ---
    print()
    print("=" * 60)
    print("TEST 4: GET /ari/bridges")
    print("=" * 60)
    try:
        resp = requests.get(f"{base}/bridges", auth=auth, timeout=5)
        if resp.status_code == 200:
            bridges = resp.json()
            print(f"  Active bridges       : {len(bridges)}")
            print(f"  Status               : PASS")
            passed += 1
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]}")
            print(f"  Status               : FAIL")
            failed += 1
    except Exception as e:
        print(f"  Error: {e}")
        print(f"  Status               : FAIL")
        failed += 1

    # --- Summary ---
    print()
    print("=" * 60)
    total = passed + failed
    if failed == 0:
        print(f"  ALL {total} TESTS PASSED — ARI is working")
    else:
        print(f"  {passed}/{total} passed, {failed} FAILED")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
