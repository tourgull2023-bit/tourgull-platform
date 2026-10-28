"""Redis atomic monitoring lease with ownership-checked release and renewal.

Expired leases are recoverable by a new owner. An old owner cannot remove or
renew the replacement lease. External scheduling and approval are separate.
"""
from uuid import uuid4

class RedisMonitoringLease:
    KEY = "tourgull:security-monitor:single-run"
    _RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""
    _RENEW = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
    def __init__(self, client):
        if client is None:
            raise ValueError("Redis connection required")
        self._client = client
        self._token = None

    def claim(self, key: str, ttl_seconds: int) -> bool:
        if key != "audit-monitor:single-run" or type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 3600:
            raise ValueError("invalid monitoring lease")
        if self._token is not None:
            return False
        token = uuid4().hex
        if self._client.set(self.KEY, token, nx=True, ex=ttl_seconds) is True:
            self._token = token
            return True
        return False

    def renew(self, key: str, ttl_seconds: int) -> bool:
        if key != "audit-monitor:single-run" or type(ttl_seconds) is not int or not 30 <= ttl_seconds <= 3600:
            raise ValueError("invalid monitoring lease")
        if self._token is None:
            return False
        return self._client.eval(self._RENEW, 1, self.KEY, self._token, ttl_seconds) == 1

    def release(self, key: str) -> None:
        if key != "audit-monitor:single-run":
            raise ValueError("invalid monitoring lease")
        token = self._token
        self._token = None
        if token is not None:
            self._client.eval(self._RELEASE, 1, self.KEY, token)
