"""Integration tests for bounded audit monitoring and alert dispatch."""
from datetime import datetime, timezone
import app.audit_operations as operations
from app.audit_alerting import AlertSeverity, IntegrityAlert
from app.audit_operations import run_integrity_monitor

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)

class MemoryDedup:
    def __init__(self):
        self.keys = set()
    def claim(self, key, ttl_seconds):
        if key in self.keys:
            return False
        self.keys.add(key)
        return True
    def release(self, key):
        self.keys.discard(key)

class Sender:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []
    def send(self, envelope):
        self.sent.append(envelope)
        if self.fail:
            raise RuntimeError("private-provider-error")

def test_critical_alert_delivered_and_duplicate_suppressed(monkeypatch):
    monkeypatch.setattr(operations, "assess_integrity", lambda session, *, limit: IntegrityAlert(
        AlertSeverity.CRITICAL, "integrity_mismatch", 5, 2
    ))
    sender, store = Sender(), MemoryDedup()
    first = run_integrity_monitor(session=object(), now=NOW, adapter=sender, dedup=store)
    second = run_integrity_monitor(session=object(), now=NOW, adapter=sender, dedup=store)
    assert (first.alert.severity, first.dispatch.status) == (AlertSeverity.CRITICAL, "delivered")
    assert second.dispatch.status == "duplicate_suppressed"
    assert len(sender.sent) == 1

def test_healthy_scan_never_sends(monkeypatch):
    monkeypatch.setattr(operations, "assess_integrity", lambda session, *, limit: IntegrityAlert(
        AlertSeverity.OK, "sample_verified", 10, 0
    ))
    sender = Sender()
    outcome = run_integrity_monitor(session=object(), now=NOW, adapter=sender, dedup=MemoryDedup())
    assert outcome.dispatch.status == "no_alert"
    assert sender.sent == []

def test_scan_failure_alert_is_not_silently_healthy(monkeypatch):
    monkeypatch.setattr(operations, "assess_integrity", lambda session, *, limit: IntegrityAlert(
        AlertSeverity.ERROR, "scan_unavailable", 0, 0
    ))
    outcome = run_integrity_monitor(session=object(), now=NOW, adapter=None, dedup=None)
    assert outcome.alert.severity == AlertSeverity.ERROR
    assert outcome.dispatch.status == "delivery_unavailable"

def test_delivery_failure_is_reported_without_secret(monkeypatch):
    monkeypatch.setattr(operations, "assess_integrity", lambda session, *, limit: IntegrityAlert(
        AlertSeverity.CRITICAL, "integrity_mismatch", 1, 1
    ))
    outcome = run_integrity_monitor(
        session=object(), now=NOW, adapter=Sender(fail=True),
        dedup=MemoryDedup(), retries=0,
    )
    assert outcome.dispatch.status == "delivery_failed"
    assert "private-provider-error" not in repr(outcome)
