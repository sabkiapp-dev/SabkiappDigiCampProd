"""Ed25519 (EdDSA) JWT generation for central-to-gateway authentication.

DigiCampServer signs tokens with the Ed25519 private key.
Gateway hosts verify them with the corresponding public key.
"""

import datetime
import jwt
from django.conf import settings

ISSUER = "digicamp"
AUDIENCE = "gateway"
DEFAULT_TTL_SECONDS = 60


def generate_host_token(host_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Generate a short-lived Ed25519-signed JWT for authenticating to a gateway host."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=ttl_seconds),
        "host_id": host_id,
    }
    return jwt.encode(payload, settings.HOST_ED25519_PRIVATE_KEY, algorithm="EdDSA")
