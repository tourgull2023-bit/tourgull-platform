"""Audit integrity tags for detecting changes to individual stored records.

HMAC verifies field integrity, not deletion, rollback, ordering, or privileged
database tampering. Store signing keys outside the database; rotate with care.
"""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from app.security_audit_model import SecurityAuditEvent


def _key() -> bytes:
    key = os.getenv("TOURGULL_AUDIT_HMAC_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise RuntimeError("audit integrity key not configured")
    return key.encode("utf-8")


def _timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise ValueError("missing audit timestamp")
    # SQLite may return naive UTC timestamps; all newly created timestamps are UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _payload(event: SecurityAuditEvent) -> bytes:
    fields = (
        event.event_id, _timestamp(event.occurred_at), event.event_type,
        event.outcome, event.reason, event.subject_fingerprint or "",
    )
    if any(not isinstance(field, str) for field in fields):
        raise ValueError("invalid audit record")
    # Length-prefixed encoding prevents ambiguous concatenations.
    return b"".join(len(field.encode("utf-8")).to_bytes(4, "big") + field.encode("utf-8") for field in fields)


def sign_audit_event(event: SecurityAuditEvent) -> str:
    return hmac.new(_key(), _payload(event), hashlib.sha256).hexdigest()


def verify_audit_event(event: SecurityAuditEvent) -> bool:
    """Fail closed for legacy, malformed, or modified rows."""
    try:
        if not isinstance(event.integrity_tag, str) or len(event.integrity_tag) != 64:
            return False
        expected = sign_audit_event(event)
        return hmac.compare_digest(expected, event.integrity_tag)
    except (ValueError, RuntimeError, OverflowError, TypeError):
        return False
