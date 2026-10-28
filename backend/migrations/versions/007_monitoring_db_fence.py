"""Database generation fencing for audit monitoring results."""
from alembic import op
import sqlalchemy as sa

revision = "007_monitoring_db_fence"
down_revision = "006_audit_key_rotation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitoring_fences",
        sa.Column("name", sa.String(length=100), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
    )
    op.create_table(
        "monitoring_results",
        sa.Column("name", sa.String(length=100), primary_key=True),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=4096), nullable=False),
    )
    op.execute("INSERT INTO monitoring_fences (name, generation) VALUES ('audit-integrity', 0)")


def downgrade():
    op.drop_table("monitoring_results")
    op.drop_table("monitoring_fences")
