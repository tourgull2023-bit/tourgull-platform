"""Security regression checks for authentication and authorization boundaries."""
import pytest
import jwt
from app import authentication as auth
from app.access_policy import AccessRequest
from app.authentication import AuthenticatedIdentity
from app.trusted_membership import evaluate_trusted_membership


@pytest.mark.parametrize("header", [
    "Bearer a b", "Bearer a\tb", "Bearer a\nb", "Basic token", "Bearer ",
    "Bearer " + "x" * 8193,
])
def test_malformed_bearer_headers_rejected(header):
    with pytest.raises(auth.AuthenticationError):
        auth.verify_bearer_token(header)


@pytest.mark.parametrize("issuer,jwks", [
    ("http://insecure.example", "https://id.example/keys"),
    ("https://id.example", "http://insecure.example/keys"),
    ("", "https://id.example/keys"),
])
def test_insecure_or_missing_oidc_configuration_rejected(monkeypatch, issuer, jwks):
    monkeypatch.setenv("TOURGULL_OIDC_ISSUER", issuer)
    monkeypatch.setenv("TOURGULL_OIDC_AUDIENCE", "tourgull-api")
    monkeypatch.setenv("TOURGULL_OIDC_JWKS_URL", jwks)
    with pytest.raises(auth.AuthenticationError, match="identity_provider_not_configured"):
        auth.verify_bearer_token("Bearer valid-looking-token")


def test_unknown_stored_role_denied_without_privilege_escalation():
    class Membership:
        role = "superuser"
        organization_id = "org-1"
        country_code = "BD"
    class Result:
        def scalar_one_or_none(self):
            return Membership()
    class Session:
        def execute(self, statement):
            return Result()
    request = AccessRequest(1, "catalog", "lookup_product", "org-1", "BD")
    result = evaluate_trusted_membership(Session(), AuthenticatedIdentity("user", "https://id.example"), request)
    assert result.allowed is False
    assert result.reason == "unknown_role"


def test_invalid_identity_rejected_before_database():
    class NoDatabase:
        def execute(self, statement):
            raise AssertionError("database must not be queried")
    request = AccessRequest(1, "catalog", "lookup_product", "org-1", "BD")
    for identity in (None, "user", AuthenticatedIdentity("", "https://id.example"),
                     AuthenticatedIdentity("user", "http://insecure.example")):
        assert not evaluate_trusted_membership(NoDatabase(), identity, request).allowed
