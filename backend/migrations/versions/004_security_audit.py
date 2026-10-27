"""Create privacy-minimizing security audit event storage."""
from alembic import op
import sqlalchemy as sa

revision = "004_security_audit"
down_revision = "003_membership_issuer"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "security_audit_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(8), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("subject_fingerprint", sa.String(64), nullable=True),
        sa.CheckConstraint("outcome IN ('allow','deny')", name="ck_audit_outcome"),
    )

def downgrade():
    op.drop_table("security_audit_events")
