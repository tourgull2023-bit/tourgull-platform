"""Explicitly authorized, single-run audit monitoring execution boundary.

This is NOT a background scheduler or production health endpoint. An external
trusted scheduler must supply its approved authorization and an atomic run lock.
No credentials, raw events or private error messages are returned.
"""
from dataclasses import dataclass
from time import monotonic
from datetime import datetime, timezone
from typing import Protocol
from app.audit_operations import run_integrity_monitor

class RunLock(Protocol):
    def claim(self, key: str, ttl_seconds: int) -> bool: ...
    def release(self, key: str) -> None: ...

@dataclass(frozen=True)
class RunReport:
    status: str
    severity: str
    examined: int
    invalid: int
    delivery_status: str

def execute_authorized_monitoring(
    *, authorized: bool, lock: RunLock, session, now: datetime,
    adapter, dedup, scan_limit: int = 1000, lock_ttl: int = 300,
    max_run_seconds: int = 240,
) -> RunReport:
    if authorized is not True:
        return RunReport("denied", "unknown", 0, 0, "not_attempted")
    if type(lock_ttl) is not int or not 30 <= lock_ttl <= 3600:
        raise ValueError("invalid lock expiry")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    if type(max_run_seconds) is not int or not 1 <= max_run_seconds < lock_ttl:
        raise ValueError("invalid run time budget")
    if lock is None:
        return RunReport("unavailable", "unknown", 0, 0, "not_attempted")
    key = "audit-monitor:single-run"
    try:
        acquired = lock.claim(key, lock_ttl)
    except Exception:
        return RunReport("unavailable", "unknown", 0, 0, "not_attempted")
    if not acquired:
        return RunReport("already_running", "unknown", 0, 0, "not_attempted")
    started = monotonic()
    try:
        outcome = run_integrity_monitor(
            session=session, now=now, adapter=adapter, dedup=dedup,
            scan_limit=scan_limit,
        )
        elapsed = monotonic() - started
        # This is a post-execution deadline check, NOT preemptive cancellation.
        # A lost Redis lease must never be reported as a successful run.
        if elapsed >= max_run_seconds:
            return RunReport("timed_out", "unknown", 0, 0, "unknown")
        renew = getattr(lock, "renew", None)
        if callable(renew):
            try:
                if renew(key, lock_ttl) is not True:
                    return RunReport("lease_lost", "unknown", 0, 0, "unknown")
            except Exception:
                return RunReport("lease_lost", "unknown", 0, 0, "unknown")
        return RunReport(
            "completed" if outcome.dispatch.status in ("delivered", "duplicate_suppressed", "no_alert") else "degraded",
            outcome.alert.severity.value, outcome.alert.examined,
            outcome.alert.invalid, outcome.dispatch.status,
        )
    except Exception:
        return RunReport("degraded", "unknown", 0, 0, "not_attempted")
    finally:
        try:
            lock.release(key)
        except Exception:
            pass
