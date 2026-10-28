"""Redis alert deduplication tests without external infrastructure."""
import pytest
from app.audit_redis_dedup import RedisAlertDedup

KEY = "audit-integrity:integrity_mismatch:123"

class FakeRedis:
    def __init__(self):
        self.values = {}
        self.calls = []
    def set(self, key, value, *, nx, ex):
        self.calls.append(("set", key, nx, ex))
        if key in self.values:
            return None
        self.values[key] = value
        return True
    def eval(self, script, count, key, token):
        self.calls.append(("eval", key))
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0

def test_atomic_claim_and_duplicate_suppression():
    redis = FakeRedis()
    first, second = RedisAlertDedup(redis), RedisAlertDedup(redis)
    assert first.claim(KEY, 900) is True
    assert second.claim(KEY, 900) is False
    assert redis.calls[0][2:] == (True, 900)

def test_release_uses_token_comparison():
    redis = FakeRedis()
    store = RedisAlertDedup(redis)
    assert store.claim(KEY, 900)
    redis.values["tourgull:security-alerts:" + KEY] = "different-worker-token"
    store.release(KEY)
    assert redis.values["tourgull:security-alerts:" + KEY] == "different-worker-token"

def test_release_allows_retry_after_failed_delivery():
    redis = FakeRedis()
    store = RedisAlertDedup(redis)
    assert store.claim(KEY, 900)
    store.release(KEY)
    assert store.claim(KEY, 900)

@pytest.mark.parametrize("key,ttl", [("wrong-prefix", 900), (KEY, 0), (KEY, 86401), (KEY, True)])
def test_invalid_claim_rejected(key, ttl):
    with pytest.raises(ValueError):
        RedisAlertDedup(FakeRedis()).claim(key, ttl)

def test_unapproved_namespace_rejected():
    with pytest.raises(ValueError):
        RedisAlertDedup(FakeRedis(), prefix="other:")
