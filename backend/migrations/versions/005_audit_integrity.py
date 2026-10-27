"""Add integrity tags without fabricating signatures for legacy events."""
from alembic import op
import sqlalchemy as sa

revision = "005_audit_integrity"
down_revision = "004_security_audit"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("security_audit_events", sa.Column("integrity_tag", sa.String(64), nullable=True))

def downgrade():
    op.drop_column("security_audit_events", "integrity_tag")
