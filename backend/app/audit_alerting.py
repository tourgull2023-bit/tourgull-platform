"""Privacy-safe audit integrity alert assessment, without external delivery.

Monitoring must run under an independently authorized operator/scheduler.
Never include tokens, subjects, fingerprints, keys, or raw audit rows in alerts.
"""
from dataclasses import dataclass
from enum import Enum
from app.audit_monitoring import IntegrityScan, scan_audit_integrity

class AlertSeverity(str, Enum):
    OK = "ok"
    CRITICAL = "critical"
    ERROR = "error"

@dataclass(frozen=True)
class IntegrityAlert:
    severity: AlertSeverity
    code: str
    examined: int
    invalid: int

def assess_integrity(session, *, limit: int = 1000) -> IntegrityAlert:
    """Return an alert even when scanning fails; never report failures as healthy.

    A zero-row result is explicitly inconclusive, not a healthy audit system.
    """
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("invalid scan limit")
    try:
        result = scan_audit_integrity(session, limit=limit)
    except Exception:
        return IntegrityAlert(AlertSeverity.ERROR, "scan_unavailable", 0, 0)
    if not isinstance(result, IntegrityScan):
        return IntegrityAlert(AlertSeverity.ERROR, "scan_unavailable", 0, 0)
    if result.invalid:
        return IntegrityAlert(AlertSeverity.CRITICAL, "integrity_mismatch", result.examined, result.invalid)
    if result.examined == 0:
        return IntegrityAlert(AlertSeverity.ERROR, "no_records_examined", 0, 0)
    return IntegrityAlert(AlertSeverity.OK, "sample_verified", result.examined, 0)
