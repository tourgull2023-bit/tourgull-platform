"""Add scoped trusted memberships (foundation only)."""
from alembic import op
import sqlalchemy as sa

revision = "002_trusted_memberships"
down_revision = "001_platform_settings"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "trusted_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject_id", sa.String(255), nullable=False),
        sa.Column("organization_id", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("subject_id", "organization_id", "country_code", name="uq_membership_scope"),
        sa.CheckConstraint("status IN ('active','suspended','revoked')", name="ck_membership_status"),
        sa.CheckConstraint("role IN ('global_admin','country_admin','supplier_admin','guest')", name="ck_membership_role"),
        sa.CheckConstraint("length(country_code) = 2 AND country_code = upper(country_code)", name="ck_membership_country"),
    )
    op.create_index("ix_trusted_memberships_subject_id", "trusted_memberships", ["subject_id"])
    op.create_index("ix_trusted_memberships_organization_id", "trusted_memberships", ["organization_id"])

def downgrade():
    op.drop_index("ix_trusted_memberships_organization_id", table_name="trusted_memberships")
    op.drop_index("ix_trusted_memberships_subject_id", table_name="trusted_memberships")
    op.drop_table("trusted_memberships")
