"""Trusted identity-to-authorization boundary.

The membership resolver must read from a trusted server-side source, never JWT
role, organization or country claims. No production membership store is wired yet.
"""
from dataclasses import dataclass
from typing import Protocol

from app.authentication import AuthenticatedIdentity, verify_bearer_token
from app.access_policy import AccessDecision, AccessRequest, Principal, Role, evaluate_access


@dataclass(frozen=True)
class TrustedMembership:
    subject_id: str
    issuer: str
    role: Role
    organization_id: str
    country_code: str
    active: bool


class MembershipResolver(Protocol):
    def resolve(self, issuer: str, subject_id: str) -> TrustedMembership | None:
        """Look up current membership from a trusted server-side system."""


class UnconfiguredMembershipResolver:
    def resolve(self, issuer: str, subject_id: str) -> None:
        return None


def authorize_identity(
    identity: AuthenticatedIdentity,
    request: AccessRequest,
    resolver: MembershipResolver,
) -> AccessDecision:
    """Fail closed when membership is missing, mismatched, or inactive."""
    if not isinstance(identity, AuthenticatedIdentity) or not isinstance(request, AccessRequest):
        return AccessDecision(False, "invalid_context")
    if not identity.subject_id or not identity.issuer:
        return AccessDecision(False, "invalid_identity")
    try:
        membership = resolver.resolve(identity.issuer, identity.subject_id)
    except Exception:
        return AccessDecision(False, "membership_unavailable")
    if not isinstance(membership, TrustedMembership):
        return AccessDecision(False, "membership_not_found")
    if (membership.active is not True or membership.subject_id != identity.subject_id
            or membership.issuer != identity.issuer):
        return AccessDecision(False, "membership_invalid")
    return evaluate_access(
        Principal(identity.subject_id, membership.role,
                  membership.organization_id, membership.country_code),
        request,
    )


def authorize_bearer(
    authorization: str | None,
    request: AccessRequest,
    resolver: MembershipResolver,
) -> AccessDecision:
    """Verify the signed bearer token before looking up trusted membership."""
    from app.authentication import AuthenticationError
    try:
        identity = verify_bearer_token(authorization)
    except AuthenticationError:
        return AccessDecision(False, "unauthenticated")
    return authorize_identity(identity, request, resolver)
