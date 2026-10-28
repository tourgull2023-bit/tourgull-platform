"""Fail-closed lease heartbeat for an externally managed monitoring worker.

This helper renews an owned Redis lease while work runs. It does not cancel
blocking I/O or fence database writes: production must use an isolated worker
with a hard timeout and fencing before enabling scheduled execution.
"""
from threading import Event, Thread

class MonitoringHeartbeat:
    def __init__(self, lease, *, key="audit-monitor:single-run", ttl_seconds=300, interval_seconds=30):
        if lease is None or not callable(getattr(lease, "renew", None)):
            raise ValueError("renewable lease required")
        if type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 3600:
            raise ValueError("invalid lease ttl")
        if type(interval_seconds) is not int or not 1 <= interval_seconds < ttl_seconds // 2:
            raise ValueError("invalid heartbeat interval")
        if key != "audit-monitor:single-run":
            raise ValueError("invalid lease key")
        self.lease, self.key, self.ttl = lease, key, ttl_seconds
        self.interval = interval_seconds
        self._stop = Event()
        self._thread = None
        self.lost = False

    def _loop(self):
        while not self._stop.wait(self.interval):
            try:
                if self.lease.renew(self.key, self.ttl) is True:
                    continue
            except Exception:
                pass
            self.lost = True
            self._stop.set()
            return

    def start(self):
        if self._thread is not None:
            raise RuntimeError("heartbeat already started")
        self._thread = Thread(target=self._loop, name="tourgull-monitor-lease-heartbeat", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1)
        return not self.lost

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
