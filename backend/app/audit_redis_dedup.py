"""Redis-backed atomic alert deduplication.

Requires a dedicated, access-controlled Redis deployment. Do not use a shared
untrusted cache namespace for security alerts.
"""
from redis import Redis
from uuid import uuid4

class RedisAlertDedup:
    def __init__(self, client: Redis, *, prefix: str = "tourgull:security-alerts:"):
        if client is None or prefix != "tourgull:security-alerts:":
            raise ValueError("approved alert Redis namespace required")
        self._client = client
        self._prefix = prefix
        self._claims: dict[str, str] = {}

    def claim(self, key: str, ttl_seconds: int) -> bool:
        if not isinstance(key, str) or not key.startswith("audit-integrity:"):
            raise ValueError("invalid alert key")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 86400:
            raise ValueError("invalid alert expiry")
        token = uuid4().hex
        result = self._client.set(self._prefix + key, token, nx=True, ex=ttl_seconds)
        if result is True:
            self._claims[key] = token
            return True
        return False

    def release(self, key: str) -> None:
        token = self._claims.pop(key, None)
        if token is None:
            return
        script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            return redis.call("DEL", KEYS[1])
        end
        return 0
        """
        self._client.eval(script, 1, self._prefix + key, token)
