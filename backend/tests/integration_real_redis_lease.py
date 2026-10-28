"""Real Redis lease integration: run only in disposable Docker CI environment.

Requires REDIS_URL and uses the same RedisMonitoringLease implementation as
the supervisor. No fake Redis or mocked EVAL. Do not run against production.
"""
import os
import time
import unittest
from redis import Redis
from app.audit_monitor_lease import RedisMonitoringLease

class RealRedisLeaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = os.environ.get("REDIS_URL")
        if not url:
            raise RuntimeError("REDIS_URL required for real Redis integration")
        cls.redis = Redis.from_url(url, socket_connect_timeout=3)
        cls.redis.ping()

    def setUp(self):
        # This suite is intentionally restricted to a disposable test database.
        if os.environ.get("TOURGULL_REDIS_INTEGRATION_TEST") != "1":
            self.fail("Explicit disposable Redis test opt-in required")
        self.redis.delete(RedisMonitoringLease.KEY)

    def tearDown(self):
        self.redis.delete(RedisMonitoringLease.KEY)

    def test_atomic_claim_and_ownership_safe_release(self):
        first = RedisMonitoringLease(self.redis)
        second = RedisMonitoringLease(self.redis)
        self.assertTrue(first.claim("audit-monitor:single-run", 30))
        self.assertFalse(second.claim("audit-monitor:single-run", 30))
        self.assertTrue(first.renew("audit-monitor:single-run", 30))
        first.release("audit-monitor:single-run")
        self.assertTrue(second.claim("audit-monitor:single-run", 30))
        first.release("audit-monitor:single-run")
        self.assertTrue(second.renew("audit-monitor:single-run", 30))
        second.release("audit-monitor:single-run")
        self.assertIsNone(self.redis.get(RedisMonitoringLease.KEY))

    def test_expired_owner_cannot_renew_or_release_replacement(self):
        first = RedisMonitoringLease(self.redis)
        second = RedisMonitoringLease(self.redis)
        self.assertTrue(first.claim("audit-monitor:single-run", 30))
        # Simulate expiry without a 30-second sleep, preserving actual Redis TTL behavior.
        self.assertTrue(self.redis.expire(RedisMonitoringLease.KEY, 1))
        time.sleep(1.2)
        self.assertTrue(second.claim("audit-monitor:single-run", 30))
        self.assertFalse(first.renew("audit-monitor:single-run", 30))
        first.release("audit-monitor:single-run")
        self.assertTrue(second.renew("audit-monitor:single-run", 30))
        second.release("audit-monitor:single-run")

    def test_rejects_invalid_claim_and_renew(self):
        lease = RedisMonitoringLease(self.redis)
        with self.assertRaises(ValueError):
            lease.claim("wrong-key", 30)
        with self.assertRaises(ValueError):
            lease.claim("audit-monitor:single-run", 0)
        self.assertFalse(lease.renew("audit-monitor:single-run", 30))

if __name__ == "__main__":
    unittest.main()
