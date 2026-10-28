"""Monitoring supervisor fail-closed recovery tests."""
import app.audit_worker_supervisor as supervisor
from app.audit_isolated_worker import WorkerResult

class Lease:
    def __init__(self, claim=True, renew=True):
        self.claim_ok, self.renew_ok = claim, renew
        self.released = 0
    def claim(self, key, ttl):
        return self.claim_ok
    def renew(self, key, ttl):
        return self.renew_ok
    def release(self, key):
        self.released += 1

class Heartbeat:
    def __init__(self, lease, **kwargs):
        self.lost = not lease.renew_ok
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass

def test_denied_never_claims_or_runs(monkeypatch):
    lease = Lease()
    monkeypatch.setattr(supervisor, "run_bounded_worker", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ran")))
    assert supervisor.supervise_monitoring(authorized=False, lease=lease, job=None).status == "denied"
    assert lease.released == 0

def test_overlap_does_not_release_someone_elses_lease():
    lease = Lease(claim=False)
    assert supervisor.supervise_monitoring(authorized=True, lease=lease, job=None).status == "already_running"
    assert lease.released == 0

def test_worker_outcomes_and_cleanup(monkeypatch):
    monkeypatch.setattr(supervisor, "MonitoringHeartbeat", Heartbeat)
    for status in ("completed", "timed_out", "failed", "termination_failed", "unavailable"):
        lease = Lease()
        monkeypatch.setattr(supervisor, "run_bounded_worker", lambda **kwargs: WorkerResult(status))
        result = supervisor.supervise_monitoring(authorized=True, lease=lease, job=None)
        assert result.status == status
        assert lease.released == 1

def test_lost_lease_overrides_success(monkeypatch):
    monkeypatch.setattr(supervisor, "MonitoringHeartbeat", Heartbeat)
    monkeypatch.setattr(supervisor, "run_bounded_worker", lambda **kwargs: WorkerResult("completed"))
    lease = Lease(renew=False)
    assert supervisor.supervise_monitoring(authorized=True, lease=lease, job=None).status == "lease_lost"
    assert lease.released == 1

def test_invalid_timing_is_rejected():
    for timeout, ttl, interval in ((0, 300, 30), (300, 300, 30), (120, 300, 150), (True, 300, 30)):
        try:
            supervisor.supervise_monitoring(authorized=True, lease=Lease(), job=None,
                                            timeout_seconds=timeout, ttl_seconds=ttl,
                                            heartbeat_seconds=interval)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid timing accepted")
