"""Initial foundation schema for platform settings.

Revision ID: 001_platform_settings
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '001_platform_settings'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'platform_settings',
        sa.Column('key', sa.String(length=120), primary_key=True),
        sa.Column('value', sa.String(length=500), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table('platform_settings')
