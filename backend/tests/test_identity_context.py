"""Authorization integration tests using a controlled trusted resolver."""
from app.access_policy import AccessRequest, Role
from app.authentication import AuthenticatedIdentity, AuthenticationError
from app import identity_context as ctx


IDENTITY = AuthenticatedIdentity("subject-1", "https://issuer.example")
REQUEST = AccessRequest(1, "catalog", "lookup_product", "org-1", "BD")


class Resolver:
    def __init__(self, membership=None, error=False):
        self.membership = membership
        self.error = error
    def resolve(self, issuer, subject_id):
        if self.error:
            raise RuntimeError("database unavailable")
        return self.membership


def membership(**overrides):
    data = dict(subject_id="subject-1", issuer="https://issuer.example",
                role=Role.GUEST, organization_id="org-1", country_code="BD",
                active=True)
    data.update(overrides)
    return ctx.TrustedMembership(**data)


def test_trusted_active_membership_allows_declared_in_scope_access():
    assert ctx.authorize_identity(IDENTITY, REQUEST, Resolver(membership())).allowed


def test_default_resolver_denies_access():
    result = ctx.authorize_identity(IDENTITY, REQUEST, ctx.UnconfiguredMembershipResolver())
    assert not result.allowed


def test_missing_inactive_and_mismatched_membership_denied():
    cases = [None, membership(active=False), membership(subject_id="another"),
             membership(issuer="https://other.example"),
             membership(organization_id="org-2"), membership(country_code="US"),
             membership(role="global_admin")]
    for item in cases:
        assert not ctx.authorize_identity(IDENTITY, REQUEST, Resolver(item)).allowed


def test_resolver_failure_denied():
    result = ctx.authorize_identity(IDENTITY, REQUEST, Resolver(error=True))
    assert result == ctx.AccessDecision(False, "membership_unavailable")


def test_invalid_token_does_not_call_resolver(monkeypatch):
    def reject(header):
        raise AuthenticationError("unauthenticated")
    monkeypatch.setattr(ctx, "verify_bearer_token", reject)
    assert ctx.authorize_bearer("Bearer invalid", REQUEST, Resolver(membership())) == (
        ctx.AccessDecision(False, "unauthenticated")
    )


def test_validated_token_uses_server_membership_not_token_claims(monkeypatch):
    monkeypatch.setattr(ctx, "verify_bearer_token", lambda header: IDENTITY)
    assert ctx.authorize_bearer("Bearer verified", REQUEST, Resolver(membership())).allowed
