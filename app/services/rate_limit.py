from __future__ import annotations
import time
import redis
from app.core.config import get_settings

class RedisRateLimiter:
    def __init__(self):
        self.client = redis.Redis.from_url(get_settings().redis_url, decode_responses=True)

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now_bucket = int(time.time() // window_seconds)
        redis_key = f'rate:{key}:{now_bucket}'
        count = self.client.incr(redis_key)
        if count == 1:
            self.client.expire(redis_key, window_seconds + 5)
        remaining = max(0, limit - int(count))
        return int(count) <= limit, remaining
