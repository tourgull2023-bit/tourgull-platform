"""Regression tests for the database-local monitoring fencing boundary."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.monitoring_db_fence import (
    MonitoringFence, MonitoringResult, NAME,
    begin_monitoring_generation, write_monitoring_result,
)


@pytest.fixture
def engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[MonitoringFence.__table__, MonitoringResult.__table__])
    with Session(engine) as session:
        session.add(MonitoringFence(name=NAME, generation=0))
        session.commit()
    yield engine
    engine.dispose()


def test_replacement_generation_rejects_stale_write(engine):
    with Session(engine) as session:
        first = begin_monitoring_generation(session)
        assert first == 1
        assert write_monitoring_result(session, first, "first")
        session.commit()
    with Session(engine) as session:
        replacement = begin_monitoring_generation(session)
        assert replacement == 2
        session.commit()
    with Session(engine) as session:
        assert not write_monitoring_result(session, first, "stale")
        assert write_monitoring_result(session, replacement, "replacement")
        session.commit()
    with Session(engine) as session:
        row = session.get(MonitoringResult, NAME)
        assert row.value == "replacement"
        assert row.generation == replacement


def test_missing_fence_fails_closed(engine):
    with Session(engine) as session:
        session.delete(session.get(MonitoringFence, NAME))
        session.commit()
    with Session(engine) as session:
        with pytest.raises(RuntimeError, match="not initialized"):
            begin_monitoring_generation(session)
        assert not write_monitoring_result(session, 1, "unsafe")


@pytest.mark.parametrize("generation", [0, -1, True, "1", None])
def test_invalid_generation_rejected(engine, generation):
    with Session(engine) as session:
        with pytest.raises(ValueError, match="invalid generation"):
            write_monitoring_result(session, generation, "unsafe")


def test_result_is_not_written_before_generation_granted(engine):
    with Session(engine) as session:
        assert not write_monitoring_result(session, 1, "premature")
        assert session.get(MonitoringResult, NAME) is None


def test_same_generation_retry_is_idempotent_and_conflict_denied(engine):
    with Session(engine) as session:
        generation = begin_monitoring_generation(session)
        assert write_monitoring_result(session, generation, "original")
        session.commit()
    with Session(engine) as session:
        assert write_monitoring_result(session, generation, "original")
        assert not write_monitoring_result(session, generation, "conflicting")
        session.commit()
    with Session(engine) as session:
        row = session.get(MonitoringResult, NAME)
        assert (row.generation, row.value) == (generation, "original")
