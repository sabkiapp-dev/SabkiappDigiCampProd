#!/usr/bin/env python3
"""Generate Ed25519 (EdDSA) JWT tokens for gateway authentication.

Usage:
    # Generate a token
    python tools/generate_token.py --key ~/.ssh/id_ed25519 --user-id admin --host host1

    # With curl command
    python tools/generate_token.py --key ~/.ssh/id_ed25519 --user-id admin --host host1 \
        --curl https://host1.sabkiapp.com/authenticate

    # Extract public key (for deploying to gateway servers)
    python tools/generate_token.py --key ~/.ssh/id_ed25519 --extract-public-key
"""

import argparse
import datetime
import sys
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_ssh_private_key,
)

ISSUER = "sabkiapp"
DEFAULT_TTL = 300  # 5 minutes


def load_private_key(path: str) -> object:
    """Load an Ed25519 private key from file (OpenSSH or PEM format)."""
    raw = Path(path).expanduser().read_bytes()
    if b"OPENSSH PRIVATE KEY" in raw:
        return load_ssh_private_key(raw, password=None)
    if raw.startswith(b"-----BEGIN"):
        return load_pem_private_key(raw, password=None)
    return load_ssh_private_key(raw, password=None)


def to_pem(key) -> bytes:
    """Convert a private key object to PEM bytes for PyJWT."""
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())


def generate_token(pem_key: bytes, user_id: str, host: str, ttl: int, issuer: str = ISSUER) -> str:
    """Sign a JWT with the given Ed25519 private key."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": issuer,
        "aud": host,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=ttl),
        "user_id": user_id,
        "host": host,
    }
    return jwt.encode(payload, pem_key, algorithm="EdDSA")


def extract_public_key(key) -> str:
    """Derive the public key PEM from a private key."""
    return key.public_key().public_bytes(
        Encoding.PEM, PublicFormat.SubjectPublicKeyInfo
    ).decode()


def main():
    parser = argparse.ArgumentParser(description="Generate Ed25519 JWT tokens for gateway auth")
    parser.add_argument("--key", required=True, help="Path to Ed25519 private key (OpenSSH or PEM)")
    parser.add_argument("--user-id", help="User ID to embed in token")
    parser.add_argument("--host", help="Target gateway hostname to embed in token")
    parser.add_argument("--iss", default=ISSUER, help=f"Issuer claim (default: {ISSUER})")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL, help=f"Token TTL in seconds (default: {DEFAULT_TTL})")
    parser.add_argument("--curl", metavar="URL", help="Print a curl command targeting this URL")
    parser.add_argument("--extract-public-key", action="store_true", help="Print the public key in PEM format and exit")
    args = parser.parse_args()

    try:
        key = load_private_key(args.key)
    except Exception as e:
        print(f"Error loading key: {e}", file=sys.stderr)
        sys.exit(1)

    if args.extract_public_key:
        print(extract_public_key(key), end="")
        return

    if not args.user_id or not args.host:
        parser.error("--user-id and --host are required when generating a token")

    pem_key = to_pem(key)
    token = generate_token(pem_key, args.user_id, args.host, args.ttl, args.iss)

    print(token)

    if args.curl:
        print(f'\ncurl -X POST -H "Authorization: Bearer {token}" {args.curl}')


if __name__ == "__main__":
    main()
