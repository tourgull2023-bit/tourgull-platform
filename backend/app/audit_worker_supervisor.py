"""Explicit monitoring worker supervisor: lease, heartbeat, isolation, recovery.

Trusted caller supplies a spawn-safe job that creates its OWN connections inside
the child. Do not pass database sessions, Redis clients or adapters across the
process boundary. No automatic scheduler, API route, or production activation.
"""
from dataclasses import dataclass
from app.audit_isolated_worker import run_bounded_worker
from app.audit_monitor_heartbeat import MonitoringHeartbeat

KEY = "audit-monitor:single-run"

@dataclass(frozen=True)
class SupervisionResult:
    status: str

def supervise_monitoring(*, authorized: bool, lease, job, args=(),
                         timeout_seconds: int = 120, ttl_seconds: int = 300,
                         heartbeat_seconds: int = 30) -> SupervisionResult:
    if authorized is not True:
        return SupervisionResult("denied")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 240:
        raise ValueError("invalid timeout")
    if type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 3600 or timeout_seconds >= ttl_seconds:
        raise ValueError("invalid lease ttl")
    if type(heartbeat_seconds) is not int or not 1 <= heartbeat_seconds < ttl_seconds // 2:
        raise ValueError("invalid heartbeat interval")
    if lease is None:
        return SupervisionResult("unavailable")
    try:
        if lease.claim(KEY, ttl_seconds) is not True:
            return SupervisionResult("already_running")
    except Exception:
        return SupervisionResult("unavailable")
    try:
        with MonitoringHeartbeat(
            lease, ttl_seconds=ttl_seconds, interval_seconds=heartbeat_seconds,
        ) as heartbeat:
            result = run_bounded_worker(
                authorized=True, job=job, args=args, timeout_seconds=timeout_seconds,
            )
        if heartbeat.lost:
            return SupervisionResult("lease_lost")
        if result.status not in ("completed", "timed_out", "failed", "termination_failed", "unavailable"):
            return SupervisionResult("failed")
        return SupervisionResult(result.status)
    except Exception:
        return SupervisionResult("failed")
    finally:
        try:
            lease.release(KEY)
        except Exception:
            pass
