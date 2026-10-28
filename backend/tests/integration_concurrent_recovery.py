"""TG-ENG-001.43: concurrent Redis takeover and PostgreSQL retry fencing.

Disposable Compose integration only. This tests local concurrency, not network
partitions, distributed transactions, or external side-effect fencing.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.audit_monitor_lease import RedisMonitoringLease
import app.monitoring_db_fence as fence

assert os.getenv("TOURGULL_CONCURRENT_RECOVERY_TEST") == "1", "disposable CI opt-in required"
url = os.environ["DATABASE_URL"]
redis_url = os.environ["REDIS_URL"]
assert url.startswith(("postgresql://", "postgresql+psycopg://"))
assert "localhost" not in redis_url and "127.0.0.1" not in redis_url
redis = Redis.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
redis.ping()
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
fence.NAME = "ci-concurrent-recovery-00143"
key = "audit-monitor:single-run"
lease_key = RedisMonitoringLease.KEY
assert redis.get(lease_key) is None, "requires an unowned disposable lease"
with engine.begin() as conn:
    conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    conn.execute(text("INSERT INTO monitoring_fences(name,generation) VALUES (:n,0)"), {"n": fence.NAME})

try:
    # Simultaneous claims must elect exactly one owner.
    start = Barrier(8)
    def compete(_):
        candidate = RedisMonitoringLease(redis)
        start.wait(timeout=10)
        return candidate, candidate.claim(key, 30)

    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(compete, range(8)))
    winners = [owner for owner, granted in attempts if granted]
    assert len(winners) == 1, attempts
    old_owner = winners[0]
    assert all(not owner.renew(key, 30) for owner, granted in attempts if not granted)

    with Session(engine) as session:
        old_generation = fence.begin_monitoring_generation(session)
        assert old_generation == 1
        assert fence.write_monitoring_result(session, old_generation, "original")
        session.commit()

    # Simulate expiry without sleeping, then race replacement claimants.
    assert redis.delete(lease_key) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        attempts = list(pool.map(compete, range(8)))
    winners = [owner for owner, granted in attempts if granted]
    assert len(winners) == 1
    new_owner = winners[0]
    old_owner.release(key)
    assert not old_owner.renew(key, 30)
    assert new_owner.renew(key, 30)
    with Session(engine) as session:
        generation = fence.begin_monitoring_generation(session)
        assert generation == 2
        session.commit()

    # Two concurrent conflicting writes to one generation: one immutable winner.
    write_start = Barrier(2)
    def write(value):
        write_start.wait(timeout=10)
        with Session(engine) as session:
            accepted = fence.write_monitoring_result(session, generation, value)
            session.commit()
            return value, accepted

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write, ("replacement-A", "replacement-B")))
    assert sorted(accepted for _, accepted in outcomes) == [False, True], outcomes
    winner_value = next(value for value, accepted in outcomes if accepted)
    with engine.connect() as conn:
        row = conn.execute(text("SELECT generation,value FROM monitoring_results WHERE name=:n"), {"n": fence.NAME}).one()
    assert row == (generation, winner_value), (row, outcomes)

    with Session(engine) as session:
        assert fence.write_monitoring_result(session, generation, winner_value)
        assert not fence.write_monitoring_result(session, generation, "conflict")
        assert not fence.write_monitoring_result(session, old_generation, "stale")
        session.commit()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT generation,value FROM monitoring_results WHERE name=:n"), {"n": fence.NAME}).one() == row
    new_owner.release(key)
    assert redis.get(lease_key) is None
    print("Concurrent recovery: single lease winner, takeover, immutable DB retries passed")
finally:
    redis.delete(lease_key)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitoring_results WHERE name=:n"), {"n": fence.NAME})
        conn.execute(text("DELETE FROM monitoring_fences WHERE name=:n"), {"n": fence.NAME})
    engine.dispose()
