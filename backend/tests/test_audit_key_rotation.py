"""Audit key rotation and bounded monitoring tests."""
from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.authentication import AuthenticatedIdentity
from app.access_policy import AccessDecision
from app.security_audit import record_access_decision
from app.security_audit_model import SecurityAuditEvent
from app.audit_integrity import verify_audit_event
from app.audit_monitoring import scan_audit_integrity


def test_rotation_preserves_verification_with_old_key(monkeypatch):
    monkeypatch.setenv("TOURGULL_AUDIT_HMAC_KEY", "fingerprint-secret-at-least-32-bytes")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "signing-secret-v1-at-least-32-bytes")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v2", "signing-secret-v2-at-least-32-bytes")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        identity = AuthenticatedIdentity("subject", "https://issuer.example")
        monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v1")
        record_access_decision(session, identity, AccessDecision(False, "membership_not_found"))
        monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v2")
        record_access_decision(session, identity, AccessDecision(True, "policy_match"))
        session.commit()
        events = session.scalars(select(SecurityAuditEvent).order_by(SecurityAuditEvent.occurred_at, SecurityAuditEvent.event_id)).all()
        assert {event.integrity_key_id for event in events} == {"v1", "v2"}
        assert all(verify_audit_event(event) for event in events)
        scan = scan_audit_integrity(session)
        assert (scan.examined, scan.valid, scan.invalid, scan.healthy) == (2, 2, 0, True)
        monkeypatch.delenv("TOURGULL_AUDIT_KEY_v1")
        scan = scan_audit_integrity(session)
        assert (scan.examined, scan.valid, scan.invalid, scan.healthy) == (2, 1, 1, False)
        monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "signing-secret-v1-at-least-32-bytes")
        events[0].reason = "tampered"
        assert scan_audit_integrity(session).invalid == 1
    engine.dispose()


@pytest.mark.parametrize("limit", [0, -1, 10001, True, "10"])
def test_scan_invalid_limits(limit):
    with pytest.raises(ValueError):
        scan_audit_integrity(None, limit=limit)
