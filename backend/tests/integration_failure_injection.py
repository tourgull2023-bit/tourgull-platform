"""TG-ENG-001.41: deterministic crash-point failure injection against real stores.

Run only in disposable Docker Compose CI. These are controlled simulated
crashes/rollbacks, not process-kill or network-partition chaos tests.
Redis and PostgreSQL do not provide a shared atomic transaction.
"""
import os
import time
from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.audit_monitor_lease import RedisMonitoringLease
import app.monitoring_db_fence as fence

assert os.getenv("TOURGULL_FAILURE_INJECTION_TEST") == "1", "disposable CI opt-in required"
url = os.environ["DATABASE_URL"]
assert url.startswith(("postgresql://", "postgresql+psycopg://")), "PostgreSQL required"
redis_url = os.environ["REDIS_URL"]
assert "localhost" not in redis_url and "127.0.0.1" not in redis_url, "Compose Redis required"
redis = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
redis.ping()
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
fence.NAME = "ci-failure-injection-00141"
key = "audit-monitor:single-run"
assert redis.get(RedisMonitoringLease.KEY) is None, "requires unowned test lease"
with engine.begin() as conn:
    conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("INSERT INTO monitoring_fences (name,generation) VALUES (:n,0)"), {"n": fence.NAME})

def fence_write_stale(generation, value):
    with Session(engine) as session:
        outcome = fence.write_monitoring_result(session, generation, value)
        session.rollback()
        return outcome

def state():
    with engine.connect() as conn:
        generation = conn.execute(text("SELECT generation FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME}).scalar_one()
        row = conn.execute(text("SELECT generation,value FROM monitoring_results WHERE name=:n"), {"n": fence.NAME}).one_or_none()
    return generation, row

try:
    # Crash point A: lease acquired, before DB grant. Nothing may be persisted.
    abandoned = RedisMonitoringLease(redis)
    assert abandoned.claim(key, 30)
    assert state() == (0, None)
    assert redis.expire(RedisMonitoringLease.KEY, 1)
    time.sleep(1.2)
    assert not abandoned.renew(key, 30)

    # Replacement obtains a lease and commits the first durable generation.
    active = RedisMonitoringLease(redis)
    assert active.claim(key, 30)
    with Session(engine) as session:
        gen1 = fence.begin_monitoring_generation(session)
        assert gen1 == 1
        assert fence.write_monitoring_result(session, gen1, "committed")
        session.commit()
    assert state() == (1, (1, "committed"))

    # Idempotent retry succeeds; conflicting duplicate is rejected without mutation.
    with Session(engine) as session:
        assert fence.write_monitoring_result(session, gen1, "committed")
        assert not fence.write_monitoring_result(session, gen1, "conflicting-retry")
        session.commit()
    assert state() == (1, (1, "committed"))

    # Crash point B: grant and result staged but DB transaction rolled back.
    with Session(engine) as session:
        assert fence.begin_monitoring_generation(session) == 2
        assert fence.write_monitoring_result(session, 2, "never-committed")
        session.rollback()
    assert state() == (1, (1, "committed"))

    # Crash point C: DB grant committed, result not yet written.
    with Session(engine) as session:
        gen2 = fence.begin_monitoring_generation(session)
        assert gen2 == 2
        session.commit()
    assert state() == (2, (1, "committed"))
    assert not fence_write_stale(gen1, "stale-after-grant")
    assert state() == (2, (1, "committed"))

    # Owner crashes before writing result; replacement fences the old generation.
    assert redis.expire(RedisMonitoringLease.KEY, 1)
    time.sleep(1.2)
    replacement = RedisMonitoringLease(redis)
    assert replacement.claim(key, 30)
    assert not active.renew(key, 30)
    with Session(engine) as session:
        gen3 = fence.begin_monitoring_generation(session)
        assert gen3 == 3
        assert fence.write_monitoring_result(session, gen3, "recovered")
        session.commit()
    assert not fence_write_stale(gen2, "stale-after-takeover")
    assert state() == (3, (3, "recovered"))
    with Session(engine) as session:
        assert fence.write_monitoring_result(session, gen3, "recovered")
        assert not fence.write_monitoring_result(session, gen3, "duplicate-conflict")
        session.commit()
    assert state() == (3, (3, "recovered"))
    abandoned.release(key)
    active.release(key)
    assert replacement.renew(key, 30)
    replacement.release(key)
    assert redis.get(RedisMonitoringLease.KEY) is None
    print("Crash-point injections: pre-grant expiry, rollback, post-grant crash, stale fencing passed")
finally:
    redis.delete(RedisMonitoringLease.KEY)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
        conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    engine.dispose()
