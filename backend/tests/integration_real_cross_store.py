"""TG-ENG-001.40: Real Redis + PostgreSQL recovery integration.

Disposable Docker Compose environment only. Both stores are real; no mocked
lease or database. This verifies coordinated generation fencing, NOT a
distributed transaction or fencing of external side effects.
"""
import os
import time
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.audit_monitor_lease import RedisMonitoringLease
import app.monitoring_db_fence as fence

assert os.getenv("TOURGULL_CROSS_STORE_TEST") == "1", "explicit disposable test opt-in required"
url = os.environ["DATABASE_URL"]
assert url.startswith(("postgresql://", "postgresql+psycopg://")), "PostgreSQL required"
redis_url = os.environ["REDIS_URL"]
assert "localhost" not in redis_url and "127.0.0.1" not in redis_url, "use disposable Compose Redis"
redis = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
redis.ping()
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
fence.NAME = "ci-cross-store-00140"
lease_key = RedisMonitoringLease.KEY
assert redis.get(lease_key) is None, "test requires an unowned disposable monitoring lease"
with engine.begin() as conn:
    conn.execute(text("DELETE FROM monitoring_results WHERE name = :n"), {"n": fence.NAME})
    conn.execute(text("DELETE FROM monitoring_fences WHERE name = :n"), {"n": fence.NAME})
    conn.execute(text("INSERT INTO monitoring_fences (name, generation) VALUES (:n, 0)"), {"n": fence.NAME})
try:
    stale = RedisMonitoringLease(redis)
    recovered = RedisMonitoringLease(redis)
    assert stale.claim("audit-monitor:single-run", 30)
    with Session(engine) as session:
        generation_1 = fence.begin_monitoring_generation(session)
        assert generation_1 == 1
        assert fence.write_monitoring_result(session, generation_1, "original")
        session.commit()

    # Simulate crash/lease expiry while DB state remains durable.
    assert redis.expire(lease_key, 1)
    time.sleep(1.2)
    assert not stale.renew("audit-monitor:single-run", 30)
    assert recovered.claim("audit-monitor:single-run", 30)
    # Recovery must first advance the DB generation, then write results.
    with Session(engine) as session:
        generation_2 = fence.begin_monitoring_generation(session)
        assert generation_2 == 2
        assert fence.write_monitoring_result(session, generation_2, "recovered")
        session.commit()

    stale.release("audit-monitor:single-run")
    assert recovered.renew("audit-monitor:single-run", 30)
    assert not stale.guarded_set("audit-monitor:single-run", "tourgull:security-monitor:result:ci-00140", "stale")
    with Session(engine) as session:
        assert not fence.write_monitoring_result(session, generation_1, "stale-overwrite")
        session.rollback()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT generation, value FROM monitoring_results WHERE name = :n"), {"n": fence.NAME}).one()
        assert row == (2, "recovered"), row

    # A failed generation grant rolls back; a still-live owner can recover.
    with Session(engine) as session:
        assert fence.begin_monitoring_generation(session) == 3
        session.rollback()
    with Session(engine) as session:
        assert fence.write_monitoring_result(session, generation_2, "after-rollback")
        session.commit()

    # Redis outage must fail closed; no new DB grant should be attempted.
    from redis.exceptions import ConnectionError as RedisConnectionError
    disconnected = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
    try:
        RedisMonitoringLease(disconnected).claim("audit-monitor:single-run", 30)
        raise AssertionError("Redis outage incorrectly granted a lease")
    except RedisConnectionError:
        pass
    with engine.connect() as conn:
        assert conn.execute(text("SELECT generation FROM monitoring_fences WHERE name = :n"), {"n": fence.NAME}).scalar_one() == 2
    recovered.release("audit-monitor:single-run")
    assert redis.get(lease_key) is None
    print("Cross-store recovery: lease expiry, stale rejection, rollback and fail-closed outage passed")
finally:
    redis.delete("tourgull:security-monitor:result:ci-00140")
    redis.delete(lease_key)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitoring_results WHERE name = :n"), {"n": fence.NAME})
        conn.execute(text("DELETE FROM monitoring_fences WHERE name = :n"), {"n": fence.NAME})
    engine.dispose()
