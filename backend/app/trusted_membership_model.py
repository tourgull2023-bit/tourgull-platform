"""Trusted membership persistence; authorization remains fail-closed."""
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

class TrustedMembership(Base):
    __tablename__ = "trusted_memberships"
    __table_args__ = (
        UniqueConstraint("issuer", "subject_id", "organization_id", "country_code", name="uq_membership_scope"),
        CheckConstraint("status IN ('active','suspended','revoked')", name="ck_membership_status"),
        CheckConstraint("role IN ('global_admin','country_admin','supplier_admin','guest')", name="ck_membership_role"),
        CheckConstraint("length(country_code) = 2 AND country_code = upper(country_code)", name="ck_membership_country"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
