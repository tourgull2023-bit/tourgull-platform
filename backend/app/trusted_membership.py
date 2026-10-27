"""Authorize only against an authenticated subject and an active stored membership.

Caller MUST validate the external token first. Never trust caller-supplied role.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.access_policy import AccessDecision, AccessRequest, Principal, Role, evaluate_access
from app.trusted_membership_model import TrustedMembership
from app.authentication import AuthenticatedIdentity

def evaluate_trusted_membership(session: Session, identity: AuthenticatedIdentity, request: AccessRequest) -> AccessDecision:
    if (not isinstance(identity, AuthenticatedIdentity) or not isinstance(identity.subject_id, str)
            or not identity.subject_id.strip() or not isinstance(identity.issuer, str)
            or not identity.issuer.startswith("https://")):
        return AccessDecision(False, "unauthenticated")
    if not isinstance(request, AccessRequest):
        return AccessDecision(False, "invalid_context")
    if not isinstance(request.organization_id, str) or not request.organization_id.strip():
        return AccessDecision(False, "invalid_context")
    if not isinstance(request.country_code, str) or len(request.country_code) != 2 or not request.country_code.isalpha() or not request.country_code.isupper():
        return AccessDecision(False, "invalid_context")
    try:
        membership = session.execute(
            select(TrustedMembership).where(
                TrustedMembership.subject_id == identity.subject_id,
                TrustedMembership.issuer == identity.issuer,
                TrustedMembership.organization_id == request.organization_id,
                TrustedMembership.country_code == request.country_code,
                TrustedMembership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            return AccessDecision(False, "membership_not_found")
        role = Role(membership.role)
    except ValueError:
        return AccessDecision(False, "unknown_role")
    except Exception:
        return AccessDecision(False, "membership_unavailable")
    return evaluate_access(
        Principal(identity.subject_id, role, membership.organization_id, membership.country_code),
        request,
    )
