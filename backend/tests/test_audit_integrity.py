"""Regression tests for audit record integrity and tampering."""
from datetime import datetime, timezone
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.authentication import AuthenticatedIdentity
from app.access_policy import AccessDecision
from app.security_audit import record_access_decision
from app.security_audit_model import SecurityAuditEvent
from app.audit_integrity import verify_audit_event


def test_persisted_audit_integrity_and_field_tampering(monkeypatch):
    monkeypatch.setenv("TOURGULL_AUDIT_HMAC_KEY", "test-audit-key-at-least-32-characters-long")
    monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v1")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "test-audit-key-at-least-32-characters-long")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        record_access_decision(session, AuthenticatedIdentity("subject-1", "https://issuer.example"),
                               AccessDecision(False, "membership_not_found"))
        session.commit()
        event = session.scalar(select(SecurityAuditEvent))
        assert verify_audit_event(event)
        event.reason = "policy_match"
        assert not verify_audit_event(event)
        session.rollback()
        event = session.scalar(select(SecurityAuditEvent))
        assert verify_audit_event(event)
        event.outcome = "allow"
        assert not verify_audit_event(event)
        session.rollback()
        event = session.scalar(select(SecurityAuditEvent))
        event.subject_fingerprint = "0" * 64
        assert not verify_audit_event(event)
    engine.dispose()


def test_unsigned_legacy_record_fails_closed(monkeypatch):
    monkeypatch.setenv("TOURGULL_AUDIT_HMAC_KEY", "test-audit-key-at-least-32-characters-long")
    monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v1")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "test-audit-key-at-least-32-characters-long")
    event = SecurityAuditEvent(
        event_id="legacy", occurred_at=datetime.now(timezone.utc),
        event_type="access_check", outcome="deny", reason="unauthenticated",
        subject_fingerprint=None, integrity_key_id=None, integrity_tag=None,
    )
    assert not verify_audit_event(event)


def test_missing_or_rotated_key_fails_verification(monkeypatch):
    monkeypatch.setenv("TOURGULL_AUDIT_HMAC_KEY", "test-audit-key-at-least-32-characters-long")
    monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v1")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "test-audit-key-at-least-32-characters-long")
    event = SecurityAuditEvent(
        event_id="test", occurred_at=datetime.now(timezone.utc),
        event_type="access_check", outcome="deny", reason="unauthenticated",
        subject_fingerprint=None, integrity_key_id="v1",
    )
    from app.audit_integrity import sign_audit_event
    event.integrity_tag = sign_audit_event(event)
    assert verify_audit_event(event)
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "another-audit-key-at-least-32-characters")
    assert not verify_audit_event(event)
    monkeypatch.delenv("TOURGULL_AUDIT_KEY_v1")
    assert not verify_audit_event(event)
