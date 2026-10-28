"""Add explicit signing-key version; existing signatures stay unverified."""
from alembic import op
import sqlalchemy as sa

revision = "006_audit_key_rotation"
down_revision = "005_audit_integrity"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("security_audit_events", sa.Column("integrity_key_id", sa.String(64), nullable=True))

def downgrade():
    op.drop_column("security_audit_events", "integrity_key_id")
