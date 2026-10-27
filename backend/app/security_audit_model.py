"""Minimal privacy-preserving security decision audit records."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"
    __table_args__ = (
        CheckConstraint("outcome IN ('allow','deny')", name="ck_audit_outcome"),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    integrity_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)  # legacy records remain unverified
    # No raw token, issuer, subject ID, organization ID or request body is persisted.
