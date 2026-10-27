"""Minimal authentication boundary. Not an identity provider or login service.

Only a configured OIDC issuer's signed RS256 JWTs are accepted. Key material,
issuer and audience must be supplied by trusted deployment configuration.
"""
import os
from dataclasses import dataclass
from functools import lru_cache

import jwt
from jwt import PyJWKClient, InvalidTokenError


class AuthenticationError(Exception):
    """Authentication failed without revealing token details."""


@dataclass(frozen=True)
class AuthenticatedIdentity:
    subject_id: str
    issuer: str


@lru_cache(maxsize=8)
def _jwk_client(url: str) -> PyJWKClient:
    return PyJWKClient(url, timeout=3, cache_jwk_set=True, lifespan=300)


def verify_bearer_token(authorization: str | None) -> AuthenticatedIdentity:
    """Verify signed access token; never trust roles or tenant claims from it."""
    if not isinstance(authorization, str):
        raise AuthenticationError("unauthenticated")
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token or len(token) > 8192:
        raise AuthenticationError("unauthenticated")
    issuer = os.getenv("TOURGULL_OIDC_ISSUER", "").rstrip("/")
    audience = os.getenv("TOURGULL_OIDC_AUDIENCE", "")
    jwks_url = os.getenv("TOURGULL_OIDC_JWKS_URL", "")
    if not issuer or not audience or not jwks_url or not jwks_url.startswith("https://"):
        raise AuthenticationError("identity_provider_not_configured")
    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"], issuer=issuer,
            audience=audience, options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            leeway=30,
        )
    except (InvalidTokenError, ValueError, jwt.PyJWKClientError, OSError) as exc:
        raise AuthenticationError("unauthenticated") from exc
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthenticationError("unauthenticated")
    return AuthenticatedIdentity(subject_id=subject, issuer=issuer)
