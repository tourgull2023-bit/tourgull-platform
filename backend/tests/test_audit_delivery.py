"""Regression tests for audit alert delivery controls."""
from datetime import datetime, timezone
import pytest
from app.audit_alerting import AlertSeverity, IntegrityAlert
from app.audit_delivery import dispatch_integrity_alert

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
ALERT = IntegrityAlert(AlertSeverity.CRITICAL, "integrity_mismatch", 8, 2)

class MemoryDedup:
    def __init__(self):
        self.keys = set()
    def claim(self, key, ttl_seconds):
        assert ttl_seconds > 0
        if key in self.keys:
            return False
        self.keys.add(key)
        return True
    def release(self, key):
        self.keys.discard(key)

class FakeSender:
    def __init__(self, fail_count=0):
        self.fail_count = fail_count
        self.sent = []
    def send(self, envelope):
        self.sent.append(envelope)
        if len(self.sent) <= self.fail_count:
            raise RuntimeError("private transport error")

def test_success_and_duplicate_suppression():
    sender, store = FakeSender(), MemoryDedup()
    first = dispatch_integrity_alert(ALERT, now=NOW, adapter=sender, dedup=store)
    second = dispatch_integrity_alert(ALERT, now=NOW, adapter=sender, dedup=store)
    assert (first.status, first.attempts) == ("delivered", 1)
    assert (second.status, second.attempts) == ("duplicate_suppressed", 0)
    assert len(sender.sent) == 1
    assert sender.sent[0].code == "integrity_mismatch"
    assert sender.sent[0].invalid == 2

def test_retry_then_success():
    sender = FakeSender(fail_count=2)
    result = dispatch_integrity_alert(ALERT, now=NOW, adapter=sender, dedup=MemoryDedup())
    assert (result.status, result.attempts) == ("delivered", 3)

def test_failed_delivery_releases_claim_and_hides_error():
    store = MemoryDedup()
    result = dispatch_integrity_alert(
        ALERT, now=NOW, adapter=FakeSender(fail_count=10), dedup=store, retries=1
    )
    assert (result.status, result.attempts) == ("delivery_failed", 2)
    assert not store.keys
    assert "private transport error" not in repr(result)

def test_unavailable_delivery_is_not_success():
    result = dispatch_integrity_alert(ALERT, now=NOW, adapter=None, dedup=None)
    assert (result.status, result.attempts) == ("delivery_unavailable", 0)

def test_ok_alert_is_not_delivered():
    ok = IntegrityAlert(AlertSeverity.OK, "sample_verified", 8, 0)
    result = dispatch_integrity_alert(ok, now=NOW, adapter=None, dedup=None)
    assert (result.status, result.attempts) == ("no_alert", 0)

@pytest.mark.parametrize("retries,window", [(True, 15), (-1, 15), (6, 15), (0, 0), (0, 1441)])
def test_invalid_settings_rejected(retries, window):
    with pytest.raises(ValueError):
        dispatch_integrity_alert(
            ALERT, now=NOW, adapter=FakeSender(), dedup=MemoryDedup(),
            retries=retries, window_minutes=window,
        )

def test_unknown_alert_code_rejected():
    unknown = IntegrityAlert(AlertSeverity.CRITICAL, "unknown", 1, 1)
    with pytest.raises(ValueError):
        dispatch_integrity_alert(unknown, now=NOW, adapter=FakeSender(), dedup=MemoryDedup())

def test_naive_time_rejected():
    with pytest.raises(ValueError):
        dispatch_integrity_alert(
            ALERT, now=datetime(2026, 10, 27), adapter=FakeSender(), dedup=MemoryDedup()
        )
