"""Privacy and fail-closed audit regression tests."""
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import Base
from app.authentication import AuthenticatedIdentity
from app.access_policy import AccessDecision
from app.security_audit import record_access_decision
from app.security_audit_model import SecurityAuditEvent
import pytest

def test_audit_records_decision_without_raw_identity(monkeypatch):
    monkeypatch.setenv("TOURGULL_AUDIT_HMAC_KEY", "test-only-audit-secret-at-least-32-bytes")
    monkeypatch.setenv("TOURGULL_AUDIT_ACTIVE_KEY_ID", "v1")
    monkeypatch.setenv("TOURGULL_AUDIT_KEY_v1", "test-only-audit-secret-at-least-32-bytes")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    identity = AuthenticatedIdentity("private-user-id", "https://issuer.example")
    with Session(engine) as session:
        record_access_decision(session, identity, AccessDecision(False, "membership_not_found"))
        record_access_decision(session, identity, AccessDecision(True, "policy_match"))
        session.commit()
        rows = session.scalars(select(SecurityAuditEvent)).all()
        assert [x.outcome for x in rows] == ["deny", "allow"]
        assert rows[0].subject_fingerprint == rows[1].subject_fingerprint
        assert len(rows[0].subject_fingerprint) == 64
        for row in rows:
            assert "private-user-id" not in repr(row.__dict__)
            assert "https://issuer.example" not in repr(row.__dict__)
    engine.dispose()

def test_missing_audit_secret_denies_recording(monkeypatch):
    monkeypatch.delenv("TOURGULL_AUDIT_HMAC_KEY", raising=False)
    class ForbiddenSession:
        def add(self, record):
            raise AssertionError("should not persist")
    with pytest.raises(RuntimeError, match="not configured"):
        record_access_decision(ForbiddenSession(), AuthenticatedIdentity("user", "https://issuer.example"), AccessDecision(True, "policy_match"))
