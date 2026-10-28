"""Isolated, bounded worker process for explicitly authorized monitoring jobs.

Use a fresh spawn process; never run blocking work in a thread and pretend it
can be killed. Only trusted, importable callables and serializable arguments
may be supplied. This is a foundation primitive, not a production scheduler.
"""
import multiprocessing as mp
from dataclasses import dataclass

@dataclass(frozen=True)
class WorkerResult:
    status: str

def _entry(queue, job, args):
    try:
        job(*args)
        queue.put("completed")
    except BaseException:
        # Never return exceptions, credentials, or event details to the parent.
        queue.put("failed")

def run_bounded_worker(*, authorized: bool, job, args=(), timeout_seconds=30) -> WorkerResult:
    if authorized is not True:
        return WorkerResult("denied")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 240:
        raise ValueError("invalid worker deadline")
    if not callable(job) or not isinstance(args, tuple):
        raise ValueError("invalid worker job")
    context = mp.get_context("spawn")
    queue = context.Queue(maxsize=1)
    process = context.Process(target=_entry, args=(queue, job, args), daemon=False)
    try:
        process.start()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(3)
            if process.is_alive():
                process.kill()
                process.join(3)
            return WorkerResult("timed_out" if not process.is_alive() else "termination_failed")
        if process.exitcode != 0:
            return WorkerResult("failed")
        try:
            return WorkerResult(queue.get(timeout=1))
        except Exception:
            return WorkerResult("failed")
    except Exception:
        return WorkerResult("unavailable")
    finally:
        if process.pid is not None and process.is_alive():
            process.kill()
            process.join(3)
        queue.close()
        queue.join_thread()
