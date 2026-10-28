"""TG-ENG-001.39: PostgreSQL transaction and generation fencing integration.

Run inside the disposable Docker Compose backend after Alembic upgrade.
Uses a dedicated test fence name by temporarily overriding the module constant;
this script runs in its own process, never in the application server.
"""
import os
import threading
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
import app.monitoring_db_fence as fence

assert os.getenv("TOURGULL_POSTGRES_FENCE_TEST") == "1", "explicit integration opt-in required"
url = os.environ["DATABASE_URL"]
assert url.startswith(("postgresql://", "postgresql+psycopg://")), "PostgreSQL required"
engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
fence.NAME = "ci-fence-00139"
with engine.begin() as conn:
    conn.execute(text("DELETE FROM monitoring_results WHERE name = :n"), {"n": fence.NAME})
    conn.execute(text("DELETE FROM monitoring_fences WHERE name = :n"), {"n": fence.NAME})
    conn.execute(text("INSERT INTO monitoring_fences (name, generation) VALUES (:n, 0)"), {"n": fence.NAME})
try:
    with Session(engine) as session:
        initial = fence.begin_monitoring_generation(session)
        assert initial == 1
        assert fence.write_monitoring_result(session, initial, "initial")
        session.commit()

    # A rolled-back grant must not invalidate the committed generation.
    with Session(engine) as session:
        assert fence.begin_monitoring_generation(session) == 2
        session.rollback()
    with Session(engine) as session:
        assert fence.write_monitoring_result(session, initial, "initial")
        session.commit()

    # Concurrent writer holds row lock; replacement grant must wait until commit.
    acquired = threading.Event()
    release = threading.Event()
    errors = []
    def old_writer():
        try:
            with Session(engine) as session:
                assert fence.write_monitoring_result(session, initial, "initial")
                acquired.set()
                assert release.wait(timeout=8)
                session.commit()
        except Exception as exc:
            errors.append(exc)
            acquired.set()

    writer = threading.Thread(target=old_writer, daemon=True)
    writer.start()
    assert acquired.wait(timeout=8), "writer never acquired row lock"
    granted = threading.Event()
    def replacement():
        try:
            with Session(engine) as session:
                assert fence.begin_monitoring_generation(session) == 2
                session.commit()
                granted.set()
        except Exception as exc:
            errors.append(exc)
            granted.set()

    newer = threading.Thread(target=replacement, daemon=True)
    newer.start()
    try:
        assert not granted.wait(timeout=0.25), "replacement bypassed held PostgreSQL row lock"
    finally:
        release.set()
    writer.join(timeout=8)
    newer.join(timeout=8)
    assert not writer.is_alive() and not newer.is_alive(), "transaction deadlock"
    assert not errors, repr(errors)
    assert granted.is_set()

    with Session(engine) as session:
        assert not fence.write_monitoring_result(session, initial, "stale")
        assert fence.write_monitoring_result(session, 2, "new")
        session.commit()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT generation, value FROM monitoring_results WHERE name = :n"), {"n": fence.NAME}).one()
        assert row == (2, "new"), row
    print("PostgreSQL fencing: rollback, concurrent row locking, stale rejection and recovery passed")
finally:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM monitoring_results WHERE name = :n"), {"n": fence.NAME})
        conn.execute(text("DELETE FROM monitoring_fences WHERE name = :n"), {"n": fence.NAME})
    engine.dispose()
