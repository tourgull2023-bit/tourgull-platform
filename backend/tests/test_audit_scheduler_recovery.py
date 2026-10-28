"""Regression tests for monitoring deadline and Redis lease-loss reporting."""
from datetime import datetime, timezone
import app.audit_scheduler as scheduler
from app.audit_alerting import AlertSeverity, IntegrityAlert
from app.audit_delivery import DispatchResult
from app.audit_operations import MonitoringOutcome

NOW = datetime(2026, 10, 27, tzinfo=timezone.utc)

class Lease:
    def __init__(self, renew_ok=True):
        self.renew_ok = renew_ok
        self.released = False
    def claim(self, key, ttl):
        return True
    def renew(self, key, ttl):
        return self.renew_ok
    def release(self, key):
        self.released = True

def healthy(**kwargs):
    return MonitoringOutcome(
        IntegrityAlert(AlertSeverity.OK, "sample_verified", 2, 0),
        DispatchResult("no_alert", 0),
    )

def test_lost_lease_fails_closed(monkeypatch):
    monkeypatch.setattr(scheduler, "run_integrity_monitor", healthy)
    lease = Lease(renew_ok=False)
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lease, session=None, now=NOW, adapter=None, dedup=None
    )
    assert report.status == "lease_lost"
    assert lease.released

def test_exceeded_budget_does_not_report_success(monkeypatch):
    monkeypatch.setattr(scheduler, "run_integrity_monitor", healthy)
    ticks = iter([0.0, 241.0])
    monkeypatch.setattr(scheduler, "monotonic", lambda: next(ticks))
    lease = Lease()
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lease, session=None, now=NOW, adapter=None, dedup=None,
        max_run_seconds=240,
    )
    assert report.status == "timed_out"
    assert lease.released

def test_lease_renewal_succeeds(monkeypatch):
    monkeypatch.setattr(scheduler, "run_integrity_monitor", healthy)
    lease = Lease()
    report = scheduler.execute_authorized_monitoring(
        authorized=True, lock=lease, session=None, now=NOW, adapter=None, dedup=None
    )
    assert report.status == "completed"
    assert lease.released

def test_invalid_budget_rejected():
    for value in (0, 300, True, -1):
        try:
            scheduler.execute_authorized_monitoring(
                authorized=True, lock=Lease(), session=None, now=NOW,
                adapter=None, dedup=None, max_run_seconds=value,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("invalid budget accepted")
