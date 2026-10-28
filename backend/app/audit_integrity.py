"""Audit integrity tags for detecting changes to individual stored records.

HMAC verifies field integrity, not deletion, rollback, ordering, or privileged
database tampering. Store signing keys outside the database; rotate with care.
"""
import hashlib
import hmac
import os
import re
from datetime import datetime, timezone
from app.security_audit_model import SecurityAuditEvent


_KEY_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

def active_key_id() -> str:
    """New records require an explicit key version; no silent legacy fallback."""
    key_id = os.getenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "")
    if not _KEY_ID.fullmatch(key_id):
        raise RuntimeError("active audit key id not configured")
    return key_id

def _key(key_id: str) -> bytes:
    if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
        raise RuntimeError("invalid audit key id")
    # Environment-based development keyring; production should use a secret manager.
    # Legacy records from 001.21 have no key id and remain unverifiable.
    key = os.getenv("TOURGULL_AUDIT_KEY_" + key_id, "")
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
        event.integrity_key_id, event.event_id, _timestamp(event.occurred_at), event.event_type,
        event.outcome, event.reason, event.subject_fingerprint or "",
    )
    if any(not isinstance(field, str) for field in fields):
        raise ValueError("invalid audit record")
    # Length-prefixed encoding prevents ambiguous concatenations.
    return b"".join(len(field.encode("utf-8")).to_bytes(4, "big") + field.encode("utf-8") for field in fields)


def sign_audit_event(event: SecurityAuditEvent) -> str:
    if not isinstance(event.integrity_key_id, str):
        raise RuntimeError("audit key version missing")
    return hmac.new(_key(event.integrity_key_id), _payload(event), hashlib.sha256).hexdigest()


def verify_audit_event(event: SecurityAuditEvent) -> bool:
    """Fail closed for legacy, malformed, or modified rows."""
    try:
        if not isinstance(event.integrity_tag, str) or len(event.integrity_tag) != 64:
            return False
        expected = sign_audit_event(event)
        return hmac.compare_digest(expected, event.integrity_tag)
    except (ValueError, RuntimeError, OverflowError, TypeError):
        return False
