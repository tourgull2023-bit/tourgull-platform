"""Controlled audit-alert dispatch foundation.

No public API, background worker, or network transport is configured here.
The caller must supply an approved authenticated delivery adapter and a
persistent atomic deduplication store before production use.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from app.audit_alerting import AlertSeverity, IntegrityAlert

_ALLOWED_CODES = frozenset({"integrity_mismatch", "scan_unavailable", "no_records_examined"})

@dataclass(frozen=True)
class AlertEnvelope:
    code: str
    severity: str
    examined: int
    invalid: int
    window_start: str
    dedup_key: str

class DeliveryAdapter(Protocol):
    def send(self, envelope: AlertEnvelope) -> None: ...

class DedupStore(Protocol):
    def claim(self, key: str, ttl_seconds: int) -> bool: ...
    def release(self, key: str) -> None: ...

@dataclass(frozen=True)
class DispatchResult:
    status: str
    attempts: int

def dispatch_integrity_alert(
    alert: IntegrityAlert, *, now: datetime, adapter: DeliveryAdapter,
    dedup: DedupStore, retries: int = 2, window_minutes: int = 15,
) -> DispatchResult:
    """Fail closed on missing delivery infrastructure; never expose raw errors.

    Dedup claims must be atomic and shared across workers. A delivery adapter
    should implement idempotent delivery using the envelope's dedup_key.
    """
    if not isinstance(alert, IntegrityAlert):
        raise ValueError("invalid alert")
    if type(retries) is not int or not 0 <= retries <= 5:
        raise ValueError("invalid retry count")
    if type(window_minutes) is not int or not 1 <= window_minutes <= 1440:
        raise ValueError("invalid dedup window")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    if alert.severity == AlertSeverity.OK:
        return DispatchResult("no_alert", 0)
    if alert.severity not in (AlertSeverity.CRITICAL, AlertSeverity.ERROR) or alert.code not in _ALLOWED_CODES:
        raise ValueError("unrecognized security alert")
    if type(alert.examined) is not int or type(alert.invalid) is not int or alert.examined < 0 or alert.invalid < 0 or alert.invalid > alert.examined:
        raise ValueError("invalid alert counts")
    if adapter is None or dedup is None:
        return DispatchResult("delivery_unavailable", 0)
    utc = now.astimezone(timezone.utc)
    bucket = int(utc.timestamp()) // (window_minutes * 60)
    window = datetime.fromtimestamp(bucket * window_minutes * 60, tz=timezone.utc)
    key = f"audit-integrity:{alert.code}:{bucket}"
    try:
        claimed = dedup.claim(key, window_minutes * 60)
    except Exception:
        return DispatchResult("delivery_unavailable", 0)
    if not claimed:
        return DispatchResult("duplicate_suppressed", 0)
    envelope = AlertEnvelope(
        code=alert.code, severity=alert.severity.value,
        examined=alert.examined, invalid=alert.invalid,
        window_start=window.isoformat(), dedup_key=key,
    )
    for attempt in range(1, retries + 2):
        try:
            adapter.send(envelope)
            return DispatchResult("delivered", attempt)
        except Exception:
            continue
    try:
        dedup.release(key)
    except Exception:
        pass
    return DispatchResult("delivery_failed", retries + 1)
