"""Identity verification boundary tests: no live IdP required."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import authentication as auth


def test_missing_or_malformed_credentials_fail_closed():
    for header in (None, "", "Basic abc", "Bearer", "Bearer ", "Bearer a" * 5000):
        with pytest.raises(auth.AuthenticationError):
            auth.verify_bearer_token(header)


def test_unconfigured_provider_fails_closed(monkeypatch):
    for name in ("TOURGULL_OIDC_ISSUER", "TOURGULL_OIDC_AUDIENCE", "TOURGULL_OIDC_JWKS_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(auth.AuthenticationError, match="identity_provider_not_configured"):
        auth.verify_bearer_token("Bearer abc")


def test_verified_subject_without_trusting_role_claims(monkeypatch):
    monkeypatch.setenv("TOURGULL_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("TOURGULL_OIDC_AUDIENCE", "tourgull-api")
    monkeypatch.setenv("TOURGULL_OIDC_JWKS_URL", "https://id.example.test/keys")
    class Key:
        key = "test-public-key"
    class Client:
        def get_signing_key_from_jwt(self, token):
            return Key()
    monkeypatch.setattr(auth, "_jwk_client", lambda url: Client())
    def decode(token, key, **kwargs):
        assert kwargs["algorithms"] == ["RS256"]
        assert kwargs["issuer"] == "https://id.example.test"
        assert kwargs["audience"] == "tourgull-api"
        assert "exp" in kwargs["options"]["require"]
        return {"sub": "user-123", "role": "global_admin", "organization_id": "forged"}
    monkeypatch.setattr(auth.jwt, "decode", decode)
    identity = auth.verify_bearer_token("Bearer example")
    assert identity == auth.AuthenticatedIdentity("user-123", "https://id.example.test")
    assert not hasattr(identity, "role")
    assert not hasattr(identity, "organization_id")


def test_invalid_signature_is_rejected(monkeypatch):
    monkeypatch.setenv("TOURGULL_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("TOURGULL_OIDC_AUDIENCE", "tourgull-api")
    monkeypatch.setenv("TOURGULL_OIDC_JWKS_URL", "https://id.example.test/keys")
    class Client:
        def get_signing_key_from_jwt(self, token):
            raise jwt.InvalidSignatureError("bad signature")
    monkeypatch.setattr(auth, "_jwk_client", lambda url: Client())
    with pytest.raises(auth.AuthenticationError, match="unauthenticated"):
        auth.verify_bearer_token("Bearer invalid")
