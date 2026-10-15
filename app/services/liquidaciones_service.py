"""Month-chunked retrieval of manifest settlements with per-month caching."""
import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple
from app.core.config import settings
from app.models.schemas import LiquidacionItem
from app.services.cache import cache
from app.services.csv_parser import CSVParser
from app.services.silogtran_client import silogtran_client

logger = logging.getLogger(__name__)
csv_parser = CSVParser()


def month_chunks(start: date, end: date) -> List[Tuple[date, date]]:
    """Calendar months (first day, last day) touched by [start, end]."""
    chunks: List[Tuple[date, date]] = []
    current = start.replace(day=1)
    while current <= end:
        last_day = current.replace(day=calendar.monthrange(current.year, current.month)[1])
        chunks.append((current, last_day))
        current = last_day + timedelta(days=1)
    return chunks


def local_today() -> date:
    """Today's date in the Silogtran installation's timezone."""
    return (datetime.now(timezone.utc) + timedelta(hours=settings.TIMEZONE_UTC_OFFSET_HOURS)).date()


def month_ttl(month_end: date) -> int:
    """Months that already ended rarely change, so they are cached longer."""
    if month_end < local_today():
        return settings.CACHE_CLOSED_MONTH_TTL_SECONDS
    return settings.CACHE_TTL_SECONDS


async def _get_month(month_start: date, month_end: date, force_refresh: bool) -> Tuple[List[LiquidacionItem], str, bool]:
    """Returns (items, generated_at, from_cache) for one whole calendar month."""
    key = f"liquidaciones:mes:{month_start:%Y-%m}"

    if not force_refresh:
        cached = await cache.get(key)
        if cached:
            return cached[0], cached[1], True

    # Prevent several requests from generating the same month at once
    async with cache.get_stampede_lock(key):
        if not force_refresh:
            cached = await cache.get(key)
            if cached:
                return cached[0], cached[1], True

        logger.info(f"Generando en Silogtran el informe del mes {month_start:%Y-%m}")
        csv_bytes = await silogtran_client.fetch_manifest_report(month_start.isoformat(), month_end.isoformat())
        items = csv_parser.parse(csv_bytes)
        await cache.set(
            key=key,
            items=items,
            start_date=month_start.isoformat(),
            end_date=month_end.isoformat(),
            ttl_seconds=month_ttl(month_end),
        )
        return items, datetime.now(timezone.utc).isoformat(), False


async def get_liquidaciones(
    fecha_inicio: str,
    fecha_fin: str,
    force_refresh: bool = False
) -> Tuple[List[LiquidacionItem], bool, str]:
    """
    Builds the requested range from whole cached months, fetching only the missing ones,
    so overlapping and larger ranges reuse what was already downloaded.
    Returns (items, from_cache, generated_at) where from_cache means no month was fetched
    and generated_at is the oldest month's generation time.
    """
    start = date.fromisoformat(fecha_inicio)
    end = date.fromisoformat(fecha_fin)

    items: List[LiquidacionItem] = []
    from_cache = True
    generated_times: List[str] = []

    for month_start, month_end in month_chunks(start, end):
        month_items, generated_at, month_cached = await _get_month(month_start, month_end, force_refresh)
        from_cache = from_cache and month_cached
        generated_times.append(generated_at)

        if start <= month_start and month_end <= end:
            items.extend(month_items)
        else:
            low = max(start, month_start).isoformat()
            high = min(end, month_end).isoformat()
            items.extend(item for item in month_items if item.fecha and low <= item.fecha <= high)

    return items, from_cache, min(generated_times)
