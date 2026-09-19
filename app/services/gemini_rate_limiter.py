import asyncio
import time
from threading import Lock

from app.logging import logger
from settings import config


class GeminiRateLimiter:
    _lock = Lock()
    _next_allowed_ts = 0.0

    @classmethod
    def acquire(cls: type['GeminiRateLimiter']) -> None:
        limit_per_minute = config.gemini.rpm_limit
        if limit_per_minute <= 0:
            return
        min_interval = 60.0 / float(limit_per_minute)
        while True:
            with cls._lock:
                now = time.monotonic()
                if now >= cls._next_allowed_ts:
                    cls._next_allowed_ts = now + min_interval
                    return
                wait_seconds = cls._next_allowed_ts - now
            logger.info('Ожидание лимитера Gemini: %.2f секунд', wait_seconds)
            time.sleep(max(0.01, wait_seconds))

    @classmethod
    async def acquire_async(cls: type['GeminiRateLimiter']) -> None:
        await asyncio.to_thread(cls.acquire)
