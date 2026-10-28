"""Explicitly invoked audit monitoring and notification orchestration.

Not scheduled, not publicly routed, and not automatically enabled. The caller
must authorize the operator and supply an approved database session, Redis
connection, and notification adapter. Never log raw audit rows or credentials.
"""
from datetime import datetime
from dataclasses import dataclass
from app.audit_alerting import assess_integrity, IntegrityAlert
from app.audit_delivery import DispatchResult, dispatch_integrity_alert

@dataclass(frozen=True)
class MonitoringOutcome:
    alert: IntegrityAlert
    dispatch: DispatchResult

def run_integrity_monitor(
    *, session, now: datetime, adapter, dedup, scan_limit: int = 1000,
    retries: int = 2, window_minutes: int = 15,
) -> MonitoringOutcome:
    """Assess integrity, then dispatch only through supplied trusted boundaries.

    Failure to scan becomes an error alert; a delivery failure is not success.
    This is bounded sampling, not evidence of complete audit-log coverage.
    """
    alert = assess_integrity(session, limit=scan_limit)
    result = dispatch_integrity_alert(
        alert, now=now, adapter=adapter, dedup=dedup,
        retries=retries, window_minutes=window_minutes,
    )
    return MonitoringOutcome(alert=alert, dispatch=result)
