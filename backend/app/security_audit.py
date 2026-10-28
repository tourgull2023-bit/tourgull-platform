"""Privacy-minimizing, transactionally persisted access-decision audit."""
import hashlib
import hmac
import os
from uuid import uuid4
from datetime import datetime, timezone
from app.audit_integrity import sign_audit_event, active_key_id
from sqlalchemy.orm import Session
from app.authentication import AuthenticatedIdentity
from app.access_policy import AccessDecision
from app.security_audit_model import SecurityAuditEvent

_ALLOWED_REASONS = frozenset({
    "policy_match", "invalid_context", "invalid_identity", "unauthenticated",
    "membership_not_found", "membership_invalid", "membership_unavailable",
    "unknown_role", "undeclared_contract", "operation_not_permitted",
    "organization_mismatch", "country_mismatch", "unknown_module",
})

def record_access_decision(session: Session, identity: AuthenticatedIdentity, decision: AccessDecision) -> None:
    """Commit in the caller's transaction; never write raw personal identifiers.

    If an audit secret is not configured, raise and deny the access request.
    """
    secret = os.getenv("TOURGULL_AUDIT_HMAC_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("audit signing key not configured")
    if not isinstance(identity, AuthenticatedIdentity) or not isinstance(decision, AccessDecision):
        raise ValueError("invalid audit context")
    if not identity.issuer or not identity.subject_id:
        raise ValueError("invalid audit identity")
    fingerprint = hmac.new(
        secret.encode("utf-8"),
        (identity.issuer + "\x00" + identity.subject_id).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    event = SecurityAuditEvent(
        event_id=str(uuid4()), occurred_at=datetime.now(timezone.utc), event_type="access_check",
        outcome="allow" if decision.allowed else "deny",
        reason=decision.reason if decision.reason in _ALLOWED_REASONS else "invalid_context",
        subject_fingerprint=fingerprint,
    )
    event.integrity_key_id = active_key_id()
    event.integrity_tag = sign_audit_event(event)
    session.add(event)
