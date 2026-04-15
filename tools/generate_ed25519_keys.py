#!/usr/bin/env python3
"""Generate an Ed25519 key pair for host JWT authentication (dev only)."""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from pathlib import Path


def main():
    private_key = Ed25519PrivateKey.generate()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    root = Path(__file__).resolve().parent.parent

    # DigiCampServer gets both keys (signs with private, can verify with public)
    dc_dir = root / "DigiCampServer" / "digicamp" / "dev_keys"
    dc_dir.mkdir(parents=True, exist_ok=True)
    (dc_dir / "host_ed25519_private.pem").write_bytes(private_pem)
    (dc_dir / "host_ed25519_public.pem").write_bytes(public_pem)

    # 32GSMgatewayServer gets only the public key (verifies tokens)
    gw_dir = root / "32GSMgatewayServer" / "gateway" / "dev_keys"
    gw_dir.mkdir(parents=True, exist_ok=True)
    (gw_dir / "host_ed25519_public.pem").write_bytes(public_pem)

    print(f"Private key: {dc_dir / 'host_ed25519_private.pem'}")
    print(f"Public key:  {dc_dir / 'host_ed25519_public.pem'}")
    print(f"Public key (gateway): {gw_dir / 'host_ed25519_public.pem'}")


if __name__ == "__main__":
    main()
