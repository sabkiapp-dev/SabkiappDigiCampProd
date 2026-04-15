"""Ed25519 (EdDSA) JWT verification for central-to-gateway authentication.

Each issuer is bound to a specific public key. A token signed by key B
cannot authenticate as issuer A — the signature check uses only the key
mapped to the claimed issuer.
"""

import functools

import jwt
from django.conf import settings
from django.http import JsonResponse


def _get_issuer_key_map() -> dict[str, str]:
    """Return {issuer: public_key_pem} mapping from settings.

    Settings expected:
        ISSUER_KEYS = {"sabkiapp": "<pem>", "other_service": "<pem>"}
    Or legacy single-key:
        CENTRAL_ED25519_PUBLIC_KEY = "<pem>"  (mapped to "sabkiapp")
    """
    explicit = getattr(settings, "ISSUER_KEYS", None)
    if explicit:
        return explicit
    # Fallback: legacy single-key config → bind to "sabkiapp"
    key = getattr(settings, "CENTRAL_ED25519_PUBLIC_KEY", "")
    if key:
        return {"sabkiapp": key}
    return {}


def verify_token(token: str) -> dict:
    """Verify an Ed25519-signed JWT. Returns decoded payload or raises.

    1. Peek at unverified 'iss' claim
    2. Lookup public key for that issuer
    3. Verify signature with ONLY that key
    """
    key_map = _get_issuer_key_map()

    # Read issuer without verifying signature
    unverified = jwt.decode(
        token,
        options={"verify_signature": False},
        algorithms=["EdDSA"],
    )
    issuer = unverified.get("iss")
    if not issuer or issuer not in key_map:
        raise jwt.InvalidTokenError(f"Unknown issuer: {issuer}")

    # Now verify with the correct key bound to this issuer
    audience = settings.API_CREDENTIALS.get("HOST", "gateway")
    return jwt.decode(
        token,
        key_map[issuer],
        algorithms=["EdDSA"],
        issuer=issuer,
        audience=audience,
    )


def extract_bearer_token(request) -> str | None:
    """Extract token from Authorization: Bearer <token> header."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def require_jwt(view_func):
    """Decorator: reject requests without a valid Ed25519 JWT Bearer token.

    On success, attaches request.jwt_payload with the decoded claims.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = extract_bearer_token(request)
        if not token:
            return JsonResponse({"error": "Missing Authorization: Bearer token"}, status=401)
        try:
            payload = verify_token(token)
        except jwt.ExpiredSignatureError:
            return JsonResponse({"error": "Token expired"}, status=401)
        except jwt.InvalidTokenError as e:
            return JsonResponse({"error": str(e)}, status=401)
        request.jwt_payload = payload
        return view_func(request, *args, **kwargs)
    return wrapper
