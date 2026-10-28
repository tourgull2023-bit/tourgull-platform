"""Isolated monitoring worker deadline, crash and authorization tests."""
import os
import time
import pytest
from app.audit_isolated_worker import run_bounded_worker

def quick_job():
    return None

def slow_job():
    time.sleep(10)

def crash_job():
    os._exit(2)

def private_failure():
    raise RuntimeError("private secret must not escape")

def test_successful_worker():
    assert run_bounded_worker(authorized=True, job=quick_job, timeout_seconds=5).status == "completed"

def test_deadline_terminates_worker():
    started = time.monotonic()
    result = run_bounded_worker(authorized=True, job=slow_job, timeout_seconds=1)
    assert result.status == "timed_out"
    assert time.monotonic() - started < 8

def test_crash_fails_closed():
    assert run_bounded_worker(authorized=True, job=crash_job, timeout_seconds=5).status == "failed"

def test_private_exception_is_sanitized():
    report = run_bounded_worker(authorized=True, job=private_failure, timeout_seconds=5)
    assert report.status == "failed"
    assert "private secret" not in repr(report)

def test_denied_never_starts_worker():
    assert run_bounded_worker(authorized=False, job=slow_job).status == "denied"

@pytest.mark.parametrize("deadline", [0, -1, True, 241])
def test_invalid_deadline_rejected(deadline):
    with pytest.raises(ValueError):
        run_bounded_worker(authorized=True, job=quick_job, timeout_seconds=deadline)
