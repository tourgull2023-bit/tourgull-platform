"""TG-ENG-001.44: fail-closed pre-grant lease authorization and outage diagnostics."""
import logging
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import Base
from app.audit_monitor_lease import RedisMonitoringLease
from app.monitoring_db_fence import MonitoringFence, MonitoringResult, NAME, begin_authorized_monitoring_generation

KEY = "audit-monitor:single-run"

class RedisStub:
    def __init__(self):
        self.owner = None
        self.outage = False
    def set(self, key, token, *, nx, ex):
        if self.outage:
            raise ConnectionError("redis down")
        if self.owner is not None:
            return None
        self.owner = token
        return True
    def eval(self, script, count, key, token, *args):
        if self.outage:
            raise ConnectionError("redis down")
        if self.owner != token:
            return 0
        return 1

@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[MonitoringFence.__table__, MonitoringResult.__table__])
    with Session(engine) as s:
        s.add(MonitoringFence(name=NAME, generation=0))
        s.commit()
    yield engine
    engine.dispose()

def generation(engine):
    with Session(engine) as s:
        return s.get(MonitoringFence, NAME).generation

def test_authorized_owner_can_advance(db):
    redis = RedisStub()
    lease = RedisMonitoringLease(redis)
    assert lease.claim(KEY, 30)
    with Session(db) as s:
        assert begin_authorized_monitoring_generation(s, lease) == 1
        s.commit()
    assert generation(db) == 1

def test_unowned_or_expired_lease_denied_without_db_mutation(db):
    redis = RedisStub()
    lease = RedisMonitoringLease(redis)
    with Session(db) as s:
        with pytest.raises(PermissionError, match="not owned"):
            begin_authorized_monitoring_generation(s, lease)
        s.rollback()
    assert lease.claim(KEY, 30)
    redis.owner = "replacement-owner"
    with Session(db) as s:
        with pytest.raises(PermissionError, match="not owned"):
            begin_authorized_monitoring_generation(s, lease)
        s.rollback()
    assert generation(db) == 0

def test_redis_outage_denied_without_db_mutation(db):
    redis = RedisStub()
    lease = RedisMonitoringLease(redis)
    assert lease.claim(KEY, 30)
    redis.outage = True
    with Session(db) as s:
        with pytest.raises(PermissionError, match="unavailable"):
            begin_authorized_monitoring_generation(s, lease)
        s.rollback()
    assert generation(db) == 0

def test_arbitrary_authority_denied(db):
    with Session(db) as s:
        with pytest.raises(PermissionError, match="authority required"):
            begin_authorized_monitoring_generation(s, object())
        s.rollback()
    assert generation(db) == 0
