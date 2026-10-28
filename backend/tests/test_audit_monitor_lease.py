"""Ownership and expiry regression tests for monitoring leases."""
from app.audit_monitor_lease import RedisMonitoringLease

class FakeRedis:
    def __init__(self):
        self.values = {}
    def set(self, key, value, *, nx, ex):
        if key in self.values:
            return None
        self.values[key] = value
        return True
    def eval(self, script, count, key, token, *args):
        if self.values.get(key) != token:
            return 0
        if "EXPIRE" in script:
            return 1
        del self.values[key]
        return 1

KEY = "audit-monitor:single-run"

def test_claim_prevents_overlap_and_release_enables_retry():
    redis = FakeRedis()
    first, second = RedisMonitoringLease(redis), RedisMonitoringLease(redis)
    assert first.claim(KEY, 300)
    assert not second.claim(KEY, 300)
    first.release(KEY)
    assert second.claim(KEY, 300)

def test_expired_old_worker_cannot_release_new_owner():
    redis = FakeRedis()
    old, new = RedisMonitoringLease(redis), RedisMonitoringLease(redis)
    assert old.claim(KEY, 300)
    redis.values.clear()  # simulate Redis TTL expiry
    assert new.claim(KEY, 300)
    old.release(KEY)
    assert RedisMonitoringLease.KEY in redis.values
    assert new.renew(KEY, 300)
    new.release(KEY)
    assert RedisMonitoringLease.KEY not in redis.values

def test_expired_old_worker_cannot_renew_new_owner():
    redis = FakeRedis()
    old, new = RedisMonitoringLease(redis), RedisMonitoringLease(redis)
    assert old.claim(KEY, 300)
    redis.values.clear()
    assert new.claim(KEY, 300)
    assert old.renew(KEY, 300) is False

def test_invalid_expiry_and_key_fail_closed():
    redis = FakeRedis()
    lease = RedisMonitoringLease(redis)
    for key, ttl in [(KEY, 0), (KEY, True), ("other", 300), (KEY, 3601)]:
        try:
            lease.claim(key, ttl)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid monitoring lease accepted")
