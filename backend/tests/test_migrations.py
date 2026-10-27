"""Migration registry and ORM schema tests (no live database required)."""
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, String
from app.db import Base
from app.models import PlatformSetting


def test_migration_has_single_head():
    config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ['002_trusted_memberships']
    assert scripts.get_revision('001_platform_settings').down_revision is None
    assert scripts.get_revision('002_trusted_memberships').down_revision == '001_platform_settings'


def test_foundation_model_is_registered():
    table = Base.metadata.tables['platform_settings']
    assert table.primary_key.columns.keys() == ['key']
    assert isinstance(table.c.key.type, String)
    assert isinstance(table.c.updated_at.type, DateTime)
    assert PlatformSetting.__table__ is table
