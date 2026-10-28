"""Security alert assessment tests: tampering, failures, and privacy."""
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from app.db import Base
from app.security_audit_model import SecurityAuditEvent
from app.audit_alerting import AlertSeverity, assess_integrity

def test_empty_scan_is_inconclusive():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        alert = assess_integrity(session)
        assert (alert.severity, alert.code) == (AlertSeverity.ERROR, "no_records_examined")
    engine.dispose()

def test_unsigned_or_tampered_record_triggers_critical_without_leak():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(SecurityAuditEvent(
            event_id="private-record", occurred_at=datetime.now(timezone.utc),
            event_type="access_check", outcome="deny", reason="membership_not_found",
            subject_fingerprint="private-fingerprint", integrity_key_id=None, integrity_tag=None,
        ))
        session.commit()
        alert = assess_integrity(session)
        assert (alert.severity, alert.code, alert.examined, alert.invalid) == (
            AlertSeverity.CRITICAL, "integrity_mismatch", 1, 1
        )
        assert "private-record" not in repr(alert)
        assert "private-fingerprint" not in repr(alert)
    engine.dispose()

def test_database_failure_never_reports_healthy():
    class BrokenSession:
        def scalars(self, statement):
            raise RuntimeError("private-database-connection-secret")
    alert = assess_integrity(BrokenSession())
    assert alert.severity == AlertSeverity.ERROR
    assert "private-database-connection-secret" not in repr(alert)

@pytest.mark.parametrize("limit", [0, -1, 10001, True, "10"])
def test_invalid_limit_rejected(limit):
    with pytest.raises(ValueError):
        assess_integrity(None, limit=limit)
