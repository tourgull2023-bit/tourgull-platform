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

    def test_connection_failure_and_recovery_fail_closed(self):
        from redis.exceptions import ConnectionError as RedisConnectionError
        broken = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2, socket_timeout=0.2)
        unavailable = RedisMonitoringLease(broken)
        with self.assertRaises(RedisConnectionError):
            unavailable.claim("audit-monitor:single-run", 30)
        self.assertIsNone(self.redis.get(RedisMonitoringLease.KEY))
        recovered = RedisMonitoringLease(self.redis)
        self.assertTrue(recovered.claim("audit-monitor:single-run", 30))
        recovered.release("audit-monitor:single-run")

    def test_crashed_worker_lease_expires_and_replacement_recovers(self):
        crashed = RedisMonitoringLease(self.redis)
        self.assertTrue(crashed.claim("audit-monitor:single-run", 30))
        # Simulate a worker crash: no release or heartbeat. Shorten TTL in real Redis.
        self.assertTrue(self.redis.expire(RedisMonitoringLease.KEY, 1))
        replacement = RedisMonitoringLease(self.redis)
        self.assertFalse(replacement.claim("audit-monitor:single-run", 30))
        time.sleep(1.2)
        self.assertTrue(replacement.claim("audit-monitor:single-run", 30))
        self.assertFalse(crashed.renew("audit-monitor:single-run", 30))
        crashed.release("audit-monitor:single-run")
        self.assertTrue(replacement.renew("audit-monitor:single-run", 30))
        replacement.release("audit-monitor:single-run")

    def test_concurrent_claims_have_exactly_one_owner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        contenders = [RedisMonitoringLease(self.redis) for _ in range(12)]
        start = Barrier(len(contenders))
        def attempt(lease):
            start.wait(timeout=10)
            return lease.claim("audit-monitor:single-run", 30)

        with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
            outcomes = list(pool.map(attempt, contenders))
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), len(contenders) - 1)
        winner = contenders[outcomes.index(True)]
        self.assertTrue(winner.renew("audit-monitor:single-run", 30))
        winner.release("audit-monitor:single-run")
        self.assertIsNone(self.redis.get(RedisMonitoringLease.KEY))

    def test_concurrent_recovery_rejects_stale_owner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        stale = RedisMonitoringLease(self.redis)
        self.assertTrue(stale.claim("audit-monitor:single-run", 30))
        self.assertTrue(self.redis.expire(RedisMonitoringLease.KEY, 1))
        time.sleep(1.2)
        contenders = [RedisMonitoringLease(self.redis) for _ in range(8)]
        start = Barrier(len(contenders))
        def recover(lease):
            start.wait(timeout=10)
            return lease.claim("audit-monitor:single-run", 30)

        with ThreadPoolExecutor(max_workers=len(contenders)) as pool:
            outcomes = list(pool.map(recover, contenders))
        self.assertEqual(outcomes.count(True), 1)
        winner = contenders[outcomes.index(True)]
        self.assertFalse(stale.renew("audit-monitor:single-run", 30))
        stale.release("audit-monitor:single-run")
        self.assertTrue(winner.renew("audit-monitor:single-run", 30))
        for i, contender in enumerate(contenders):
            if i != outcomes.index(True):
                self.assertFalse(contender.renew("audit-monitor:single-run", 30))
        winner.release("audit-monitor:single-run")

    def test_rejects_invalid_claim_and_renew(self):
        lease = RedisMonitoringLease(self.redis)
        with self.assertRaises(ValueError):
            lease.claim("wrong-key", 30)
        with self.assertRaises(ValueError):
            lease.claim("audit-monitor:single-run", 0)
        self.assertFalse(lease.renew("audit-monitor:single-run", 30))

if __name__ == "__main__":
    unittest.main()
