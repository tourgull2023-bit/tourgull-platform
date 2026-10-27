"""Server-side audit governance primitives; no public API or automatic deletion.

Operators must obtain independent approval before running retention deletion.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from app.security_audit_model import SecurityAuditEvent

@dataclass(frozen=True)
class AuditRetentionPlan:
    older_than: datetime
    eligible_count: int

def _validate_retention(days: int, now: datetime) -> datetime:
    if type(days) is not int or days < 1 or days > 36500:
        raise ValueError("invalid retention period")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware clock required")
    return now.astimezone(timezone.utc) - timedelta(days=days)

def preview_retention(session: Session, *, days: int, now: datetime) -> AuditRetentionPlan:
    """Count eligible records without mutating any audit data."""
    cutoff = _validate_retention(days, now)
    count = session.scalar(
        select(func.count()).select_from(SecurityAuditEvent).where(SecurityAuditEvent.occurred_at < cutoff)
    )
    return AuditRetentionPlan(older_than=cutoff, eligible_count=int(count or 0))

def apply_approved_retention(
    session: Session, *, days: int, now: datetime, approved: bool = False,
    legal_hold: bool = True,
) -> int:
    """Requires explicit approval and an explicitly cleared legal hold.

    Does not commit: the authorized operator must control the transaction.
    Never expose this method through a guest, supplier, or public API.
    """
    cutoff = _validate_retention(days, now)
    if approved is not True or legal_hold is not False:
        raise PermissionError("retention approval or legal-hold clearance missing")
    result = session.execute(
        delete(SecurityAuditEvent).where(SecurityAuditEvent.occurred_at < cutoff)
    )
    return int(result.rowcount or 0)
