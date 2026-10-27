"""Bind memberships to issuer, migrating legacy rows fail-closed.

Existing records cannot be trusted without an issuer, so they are revoked.
"""
from alembic import op
import sqlalchemy as sa

revision = "003_membership_issuer"
down_revision = "002_trusted_memberships"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("trusted_memberships", sa.Column("issuer", sa.String(255), nullable=True))
    op.execute("UPDATE trusted_memberships SET status = 'revoked', issuer = 'unverified:legacy' WHERE issuer IS NULL")
    op.alter_column("trusted_memberships", "issuer", nullable=False)
    op.drop_constraint("uq_membership_scope", "trusted_memberships", type_="unique")
    op.create_unique_constraint("uq_membership_scope", "trusted_memberships", ["issuer", "subject_id", "organization_id", "country_code"])

def downgrade():
    op.drop_constraint("uq_membership_scope", "trusted_memberships", type_="unique")
    op.create_unique_constraint("uq_membership_scope", "trusted_memberships", ["subject_id", "organization_id", "country_code"])
    op.drop_column("trusted_memberships", "issuer")
