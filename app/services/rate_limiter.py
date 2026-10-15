"""In-memory rate limiter using sliding window algorithm."""
import asyncio
import time
from collections import defaultdict
from typing import Dict, List
from app.core.config import settings
from app.core.exceptions import RateLimitExceededError


class SlidingWindowRateLimiter:
    """Sliding-window in-memory rate limiter per client identifier (token or IP)."""

    def __init__(self, requests_per_minute: int = 60):
        self.limit = requests_per_minute
        self.window = 60.0  # 1 minute window in seconds
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> None:
        """
        Records an attempt for `key`. Raises RateLimitExceededError if rate exceeded.
        """
        now = time.time()
        async with self._lock:
            timestamps = self._history[key]
            # Prune timestamps older than window
            cutoff = now - self.window
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) >= self.limit:
                raise RateLimitExceededError(
                    f"Ha superado el límite de {self.limit} solicitudes por minuto. Intente de nuevo en unos segundos."
                )

            timestamps.append(now)

            # Cleanup inactive keys periodically
            if len(self._history) > 1000:
                inactive = [k for k, v in self._history.items() if not v or v[-1] < cutoff]
                for k in inactive:
                    del self._history[k]


rate_limiter = SlidingWindowRateLimiter(
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE
)
