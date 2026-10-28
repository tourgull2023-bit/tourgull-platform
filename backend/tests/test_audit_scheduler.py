"""Tests for explicit monitoring authorization and operational run safety."""
from datetime import datetime, timezone
import app.audit_scheduler as scheduler
from app.audit_alerting import AlertSeverity, IntegrityAlert
from app.audit_delivery import DispatchResult
from app.audit_operations import MonitoringOutcome

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)

class Lock:
    def __init__(self, busy=False):
        self.busy = busy
        self.releases = 0
    def claim(self, key, ttl_seconds):
        assert key == "audit-monitor:single-run"
        assert ttl_seconds == 300
        return not self.busy
    def release(self, key):
        self.releases += 1

def test_unauthorized_run_never_claims_lock(monkeypatch):
    lock = Lock()
    monkeypatch.setattr(scheduler, "run_integrity_monitor", lambda **kwargs: (_ for _ in ()).throw(AssertionError("should not run")))
    report = scheduler.execute_authorized_monitoring(
        authorized=False, lock=lock, session=None, now=NOW, adapter=None, dedup=None
    )
    assert report.status == "denied"
    assert lock.releases == 0

def test_overlapping_run_is_suppressed(monkeypatch):
    lock = Lock(busy=True)
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lock, session=None, now=NOW, adapter=None, dedup=None
    )
    assert report.status == "already_running"
    assert lock.releases == 0

def test_success_reports_only_aggregates_and_releases(monkeypatch):
    lock = Lock()
    monkeypatch.setattr(scheduler, "run_integrity_monitor", lambda **kwargs: MonitoringOutcome(
        IntegrityAlert(AlertSeverity.OK, "sample_verified", 12, 0),
        DispatchResult("no_alert", 0),
    ))
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lock, session=None, now=NOW, adapter=None, dedup=None
    )
    assert (report.status, report.severity, report.examined, report.invalid) == ("completed", "ok", 12, 0)
    assert lock.releases == 1

def test_delivery_failure_is_degraded(monkeypatch):
    monkeypatch.setattr(scheduler, "run_integrity_monitor", lambda **kwargs: MonitoringOutcome(
        IntegrityAlert(AlertSeverity.CRITICAL, "integrity_mismatch", 4, 2),
        DispatchResult("delivery_failed", 3),
    ))
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=Lock(), session=None, now=NOW, adapter=None, dedup=None
    )
    assert (report.status, report.delivery_status) == ("degraded", "delivery_failed")

def test_internal_error_is_sanitized_and_lock_released(monkeypatch):
    lock = Lock()
    def fail(**kwargs):
        raise RuntimeError("private database credential")
    monkeypatch.setattr(scheduler, "run_integrity_monitor", fail)
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lock, session=None, now=NOW, adapter=None, dedup=None
    )
    assert report.status == "degraded"
    assert "private database credential" not in repr(report)
    assert lock.releases == 1
