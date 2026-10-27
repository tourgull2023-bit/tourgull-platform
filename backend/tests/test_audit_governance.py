"""Retention governance must fail closed and default to non-destructive behavior."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.security_audit_model import SecurityAuditEvent
from app.audit_governance import preview_retention, apply_approved_retention
from app.main import app

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)

def test_retention_preview_and_approval_gates():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            SecurityAuditEvent(event_id=str(uuid4()), occurred_at=NOW - timedelta(days=400),
                               event_type="access_check", outcome="deny", reason="unauthenticated"),
            SecurityAuditEvent(event_id=str(uuid4()), occurred_at=NOW - timedelta(days=5),
                               event_type="access_check", outcome="allow", reason="policy_match"),
        ])
        session.commit()
        plan = preview_retention(session, days=365, now=NOW)
        assert plan.eligible_count == 1
        assert session.query(SecurityAuditEvent).count() == 2
        with pytest.raises(PermissionError):
            apply_approved_retention(session, days=365, now=NOW)
        with pytest.raises(PermissionError):
            apply_approved_retention(session, days=365, now=NOW, approved=True)
        assert session.query(SecurityAuditEvent).count() == 2
        assert apply_approved_retention(session, days=365, now=NOW, approved=True, legal_hold=False) == 1
        session.commit()
        assert session.query(SecurityAuditEvent).count() == 1
    engine.dispose()

@pytest.mark.parametrize("days", [0, -1, 36501, True, "365"])
def test_invalid_retention_rejected(days):
    with pytest.raises(ValueError):
        preview_retention(None, days=days, now=NOW)

def test_naive_clock_rejected():
    with pytest.raises(ValueError):
        preview_retention(None, days=30, now=datetime(2026, 10, 27))


def test_no_public_retention_or_audit_read_endpoints():
    paths = {route.path for route in app.routes if hasattr(route, 'path')}
    assert not any("/audit" in path or "/retention" in path for path in paths)
