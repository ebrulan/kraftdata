"""Ingest ENTSO-E day-ahead prices for NO1-NO5 into raw/entsoe/day_ahead_prices/date=YYYY-MM-DD/.

Usage:
    python -m ingest.prices --start 2022-01-01 --end 2022-12-31
    python -m ingest.prices                      # yesterday, today and tomorrow
    python -m ingest.prices --local-root data/raw  # write locally instead of ADLS
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from datetime import date, timedelta

from dotenv import load_dotenv

from ingest.entsoe import ZONES, PricePoint, fetch_day_ahead_xml, parse_day_ahead_xml
from ingest.storage import RawStore

log = logging.getLogger(__name__)

SOURCE_PATH = "entsoe/day_ahead_prices"
MAX_DAYS_PER_REQUEST = 365


def date_chunks(start: date, end: date, size: int) -> list[tuple[date, date]]:
    chunks = []
    while start <= end:
        chunk_end = min(start + timedelta(days=size - 1), end)
        chunks.append((start, chunk_end))
        start = chunk_end + timedelta(days=1)
    return chunks


def partition_path(delivery_date: str) -> str:
    return f"{SOURCE_PATH}/date={delivery_date}/prices.jsonl"


def ingest(api_key: str, store: RawStore, start: date, end: date) -> dict[str, int]:
    """Fetch all zones for [start, end] and write one file per delivery date."""
    by_date: dict[str, list[PricePoint]] = defaultdict(list)
    for zone in ZONES:
        for chunk_start, chunk_end in date_chunks(start, end, MAX_DAYS_PER_REQUEST):
            log.info("Fetching %s %s..%s", zone, chunk_start, chunk_end)
            xml_text = fetch_day_ahead_xml(api_key, zone, chunk_start, chunk_end)
            for point in parse_day_ahead_xml(xml_text, zone):
                # The API can return neighbouring days; keep only what was asked for.
                if start.isoformat() <= point.delivery_date <= end.isoformat():
                    by_date[point.delivery_date].append(point)

    written = {}
    for delivery_date, points in sorted(by_date.items()):
        points.sort(key=lambda p: (p.zone, p.interval_start_utc))
        written[delivery_date] = store.write_jsonl(
            partition_path(delivery_date), (p.to_dict() for p in points)
        )
    log.info("Wrote %d date partitions, %d rows", len(written), sum(written.values()))
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    load_dotenv()
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=today - timedelta(days=1))
    # Day-ahead prices for tomorrow are published around 13:00 CET.
    parser.add_argument("--end", type=date.fromisoformat, default=today + timedelta(days=1))
    parser.add_argument("--local-root", default=os.getenv("RAW_LOCAL_ROOT", ""))
    args = parser.parse_args()

    store = RawStore(
        account=os.getenv("AZURE_STORAGE_ACCOUNT"),
        container=os.getenv("AZURE_STORAGE_CONTAINER", "raw"),
        local_root=args.local_root,
    )
    ingest(os.environ["ENTSOE_API_KEY"], store, args.start, args.end)


if __name__ == "__main__":
    main()
