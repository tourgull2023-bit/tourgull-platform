"""Redis-backed atomic alert deduplication.

Requires a dedicated, access-controlled Redis deployment. Do not use a shared
untrusted cache namespace for security alerts.
"""
from redis import Redis

class RedisAlertDedup:
    def __init__(self, client: Redis, *, prefix: str = "tourgull:security-alerts:"):
        if client is None or prefix != "tourgull:security-alerts:":
            raise ValueError("approved alert Redis namespace required")
        self._client = client
        self._prefix = prefix

    def claim(self, key: str, ttl_seconds: int) -> bool:
        if not isinstance(key, str) or not key.startswith("audit-integrity:"):
            raise ValueError("invalid alert key")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("invalid alert expiry")
        result = self._client.set(self._prefix + key, "claimed", nx=True, ex=ttl_seconds)
        return result is True

    def release(self, key: str) -> None:
        # Never blindly delete: a lease may have expired and been claimed
        # by another worker. A compare-and-delete token is needed for safe release.
        raise RuntimeError("unsafe release disabled")
