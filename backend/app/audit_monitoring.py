"""Read-only integrity monitoring; no audit-record mutation or public endpoint."""
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.security_audit_model import SecurityAuditEvent
from app.audit_integrity import verify_audit_event

@dataclass(frozen=True)
class IntegrityScan:
    examined: int
    valid: int
    invalid: int

    @property
    def healthy(self) -> bool:
        return self.invalid == 0

def scan_audit_integrity(session: Session, *, limit: int = 1000) -> IntegrityScan:
    """Scan a bounded deterministic batch; raise if storage unavailable.

    This is not completeness monitoring: deleted rows cannot be detected here.
    """
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("invalid scan limit")
    rows = session.scalars(
        select(SecurityAuditEvent).order_by(SecurityAuditEvent.occurred_at, SecurityAuditEvent.event_id).limit(limit)
    )
    examined = invalid = 0
    for row in rows:
        examined += 1
        if not verify_audit_event(row):
            invalid += 1
    return IntegrityScan(examined=examined, valid=examined - invalid, invalid=invalid)
