"""Heartbeat ownership and failure tests (no real worker or Redis required)."""
import pytest
from app.audit_monitor_heartbeat import MonitoringHeartbeat

class Lease:
    def __init__(self, result=True):
        self.result = result
        self.calls = 0
    def renew(self, key, ttl):
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

def test_heartbeat_renews_owned_lease():
    lease = Lease()
    hb = MonitoringHeartbeat(lease)
    hb._stop.wait = lambda interval: False if lease.calls == 0 else True
    hb._loop()
    assert lease.calls == 1
    assert hb.lost is False

@pytest.mark.parametrize("result", [False, RuntimeError("redis down")])
def test_heartbeat_fails_closed_on_lost_ownership(result):
    lease = Lease(result)
    hb = MonitoringHeartbeat(lease)
    hb._stop.wait = lambda interval: False
    hb._loop()
    assert hb.lost is True
    assert lease.calls == 1
    assert hb.stop() is False

def test_heartbeat_validates_lease_and_timing():
    for args in [
        {"lease": None},
        {"lease": Lease(), "ttl_seconds": 0},
        {"lease": Lease(), "interval_seconds": 150},
        {"lease": Lease(), "interval_seconds": True},
        {"lease": Lease(), "key": "wrong"},
    ]:
        with pytest.raises(ValueError):
            MonitoringHeartbeat(**args)

def test_context_manager_stops_cleanly():
    lease = Lease()
    with MonitoringHeartbeat(lease) as hb:
        assert hb._thread is not None
    assert hb._stop.is_set()
    assert not hb._thread.is_alive()
