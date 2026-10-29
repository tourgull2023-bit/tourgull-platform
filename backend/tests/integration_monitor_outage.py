"""TG-ENG-001.44: live Redis recovery and fail-closed PostgreSQL grants.

Disposable Compose only. An unreachable TCP endpoint simulates loss of Redis
connectivity without stopping the shared CI Redis container.
"""
import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from redis import Redis
from app.audit_monitor_lease import RedisMonitoringLease
import app.monitoring_db_fence as fence

assert os.getenv("TOURGULL_MONITOR_OUTAGE_TEST") == "1", "disposable CI opt-in required"
url = os.environ["DATABASE_URL"]
redis_url = os.environ["REDIS_URL"]
assert url.startswith(("postgresql://", "postgresql+psycopg://"))
assert "localhost" not in redis_url and "127.0.0.1" not in redis_url
live = Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
live.ping()
# The container loopback endpoint is deliberately unavailable.
unreachable = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
fence.NAME = "ci-monitor-outage-00144"
key = "audit-monitor:single-run"
assert live.get(RedisMonitoringLease.KEY) is None, "requires disposable unowned lease"
with engine.begin() as conn:
    conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("INSERT INTO monitoring_fences(name,generation) VALUES (:n,0)"), {"n": fence.NAME})

try:
    owner = RedisMonitoringLease(live)
    assert owner.claim(key, 30)
    with Session(engine) as session:
        assert fence.begin_authorized_monitoring_generation(session, owner) == 1
        assert fence.write_monitoring_result(session, 1, "before-outage")
        session.commit()

    # A real connection failure must not grant a database generation.
    lost_connection = RedisMonitoringLease(unreachable)
    lost_connection._token = owner._token  # test-only: simulate retained local token
    records = []
    class Collector(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())
    handler = Collector()
    fence.logger.addHandler(handler)
    try:
        with Session(engine) as session:
            try:
                fence.begin_authorized_monitoring_generation(session, lost_connection)
                raise AssertionError("outage unexpectedly authorized")
            except PermissionError as exc:
                assert str(exc) == "monitoring lease unavailable"
                session.rollback()
    finally:
        fence.logger.removeHandler(handler)
    assert "monitoring_generation_denied reason=redis_unavailable" in records
    assert all(owner._token not in record for record in records)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT generation FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME}).scalar_one() == 1

    # Simulate expiry/takeover, then reject the stale owner and recover.
    assert live.delete(RedisMonitoringLease.KEY) == 1
    replacement = RedisMonitoringLease(live)
    assert replacement.claim(key, 30)
    with Session(engine) as session:
        try:
            fence.begin_authorized_monitoring_generation(session, owner)
            raise AssertionError("stale owner unexpectedly authorized")
        except PermissionError as exc:
            assert str(exc) == "monitoring lease not owned"
            session.rollback()
    with Session(engine) as session:
        assert fence.begin_authorized_monitoring_generation(session, replacement) == 2
        assert fence.write_monitoring_result(session, 2, "recovered")
        assert not fence.write_monitoring_result(session, 1, "stale")
        session.commit()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT generation,value FROM monitoring_results WHERE name=:n"), {"n": fence.NAME}).one()
        assert row == (2, "recovered"), row
    replacement.release(key)
    print("Monitoring outage: denied grant, safe recovery, stale rejection, privacy-safe diagnostics passed")
finally:
    live.delete(RedisMonitoringLease.KEY)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
        conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    engine.dispose()
