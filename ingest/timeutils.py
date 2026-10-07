"""Date helpers shared by the ingestion modules.

Raw files are partitioned by calendar day in Norwegian local time, because that is how
the power market and most users think about a "day". APIs work in UTC, so these helpers
convert between the two.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

OSLO = ZoneInfo("Europe/Oslo")


def oslo_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Start and end of a Norwegian calendar day in UTC (23, 24 or 25 hours long)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=OSLO)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=OSLO)
    return start.astimezone(UTC), end.astimezone(UTC)


def oslo_date(moment: datetime) -> str:
    """Norwegian calendar date (YYYY-MM-DD) of a timezone-aware datetime."""
    return moment.astimezone(OSLO).date().isoformat()


def date_chunks(start: date, end: date, size: int) -> list[tuple[date, date]]:
    """Split [start, end] into consecutive inclusive ranges of at most `size` days."""
    chunks = []
    while start <= end:
        chunk_end = min(start + timedelta(days=size - 1), end)
        chunks.append((start, chunk_end))
        start = chunk_end + timedelta(days=1)
    return chunks
