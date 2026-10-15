"""Caching system with memory-efficient LRU, TTL, sub-range reuse, and stampede protection."""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.core.config import settings
from app.models.schemas import LiquidacionItem

logger = logging.getLogger(__name__)


class BaseCache(ABC):
    """Abstract interface for cache implementations (In-memory, Redis, etc.)."""

    @abstractmethod
    async def get(self, key: str) -> Optional[Tuple[List[LiquidacionItem], str]]:
        """Retrieves exact match for key. Returns (items, generated_at) or None."""
        pass

    @abstractmethod
    async def set(self, key: str, items: List[LiquidacionItem], start_date: str, end_date: str, ttl_seconds: Optional[int] = None) -> None:
        """Stores items for a key and date range with TTL."""
        pass

    @abstractmethod
    async def get_matching_range(self, start_date: str, end_date: str) -> Optional[Tuple[List[LiquidacionItem], str]]:
        """
        Finds a cached entry whose range fully covers [start_date, end_date]
        and returns the filtered items.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clears all cached entries."""
        pass


class CacheEntry:
    """Represents a cached dataset and metadata."""
    def __init__(
        self,
        key: str,
        items: List[LiquidacionItem],
        start_date: str,
        end_date: str,
        expires_at: float,
        generated_at: str
    ):
        self.key = key
        self.items = items
        self.start_date = start_date
        self.end_date = end_date
        self.expires_at = expires_at
        self.generated_at = generated_at

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class InMemoryCache(BaseCache):
    """
    Lightweight, thread-safe in-memory cache with LRU eviction, TTL,
    and range subset reuse, designed for Render 512MB RAM constraints.
    """

    def __init__(self, max_entries: int = 500, default_ttl: int = 900):
        self.max_entries = max_entries
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()
        self._stampede_locks: Dict[str, asyncio.Lock] = {}

    def get_stampede_lock(self, key: str) -> asyncio.Lock:
        """Returns or creates an asyncio.Lock for stampede prevention on this key."""
        if key not in self._stampede_locks:
            self._stampede_locks[key] = asyncio.Lock()
        return self._stampede_locks[key]

    async def get(self, key: str) -> Optional[Tuple[List[LiquidacionItem], str]]:
        async with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]
            if entry.is_expired():
                del self._cache[key]
                return None

            # Mark recently used for LRU
            self._cache.move_to_end(key)
            return entry.items, entry.generated_at

    async def set(
        self,
        key: str,
        items: List[LiquidacionItem],
        start_date: str,
        end_date: str,
        ttl_seconds: Optional[int] = None
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        expires_at = time.time() + ttl
        now_iso = datetime.now(timezone.utc).isoformat()

        async with self._lock:
            # Clean expired before inserting if approaching capacity
            if len(self._cache) >= self.max_entries:
                self._evict_expired_or_oldest()

            entry = CacheEntry(
                key=key,
                items=items,
                start_date=start_date,
                end_date=end_date,
                expires_at=expires_at,
                generated_at=now_iso
            )
            self._cache[key] = entry
            self._cache.move_to_end(key)
            logger.info(f"Caché guardada para clave '{key}' ({len(items)} registros, TTL: {ttl}s)")

    async def get_matching_range(self, start_date: str, end_date: str) -> Optional[Tuple[List[LiquidacionItem], str]]:
        """
        If a query is completely contained within an already cached larger range,
        reuses and filters the cached records.
        """
        async with self._lock:
            now = time.time()
            for key, entry in list(self._cache.items()):
                if entry.expires_at <= now:
                    del self._cache[key]
                    continue

                # Check if query range is within entry range:
                # entry.start_date <= start_date and entry.end_date >= end_date
                if entry.start_date <= start_date and entry.end_date >= end_date:
                    logger.info(
                        f"Rango [{start_date} a {end_date}] contenido en caché existente "
                        f"[{entry.start_date} a {entry.end_date}]"
                    )
                    # Filter items matching start_date <= item.fecha <= end_date
                    filtered = [
                        item for item in entry.items
                        if item.fecha and start_date <= item.fecha <= end_date
                    ]
                    self._cache.move_to_end(key)
                    return filtered, entry.generated_at

        return None

    def _evict_expired_or_oldest(self) -> None:
        """Evicts expired items, or the oldest item (FIFO/LRU) if none expired."""
        now = time.time()
        expired_keys = [k for k, v in self._cache.items() if v.expires_at <= now]
        for k in expired_keys:
            del self._cache[k]

        while len(self._cache) >= self.max_entries:
            # Pop oldest (first in OrderedDict)
            self._cache.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            self._stampede_locks.clear()


# Global cache instance
cache = InMemoryCache(
    max_entries=settings.MAX_CACHE_ENTRIES,
    default_ttl=settings.CACHE_TTL_SECONDS
)
