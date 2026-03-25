"""RS-256 service-to-service JWT authentication for SabkiApp → VoiceAPI."""
from __future__ import annotations

from typing import Optional, Tuple

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

ISSUER = "sabkiapp"
AUDIENCE = "sabkiapp_voip"


class ServiceJWTAuthentication(BaseAuthentication):
    """Validate Authorization: Bearer <JWT>. Returns AnonymousUser on success."""

    def authenticate(self, request) -> Optional[Tuple[AnonymousUser, None]]:  # type: ignore[override]
        auth_header: str = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        try:
            jwt.decode(
                token,
                settings.SABKIAPP_PUBLIC_KEY,
                algorithms=["RS256"],
                audience=AUDIENCE,
                issuer=ISSUER,
            )
            return (AnonymousUser(), None)
        except ExpiredSignatureError:
            raise AuthenticationFailed("Token expired")
        except InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
