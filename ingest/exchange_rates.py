"""Ingest EUR/NOK rates into raw/norges_bank/eur_nok/month=YYYY-MM/rates.jsonl.

There is at most one rate per business day, so files are partitioned by month instead of
by day. A run rewrites every month it touches in full, which keeps it idempotent.

Usage:
    python -m ingest.exchange_rates --start 2022-01-01
    python -m ingest.exchange_rates            # the current and previous month
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from datetime import date, timedelta

from dotenv import load_dotenv

from ingest.norges_bank import ExchangeRate, fetch_rates_csv, parse_rates_csv
from ingest.storage import RawStore

log = logging.getLogger(__name__)

SOURCE_PATH = "norges_bank/eur_nok"


def partition_path(month: str) -> str:
    return f"{SOURCE_PATH}/month={month}/rates.jsonl"


def month_bounds(start: date, end: date) -> tuple[date, date]:
    """Widen [start, end] to whole months, so every partition is written complete."""
    first = start.replace(day=1)
    next_month = (end.replace(day=1) + timedelta(days=32)).replace(day=1)
    return first, next_month - timedelta(days=1)


def ingest(store: RawStore, start: date, end: date) -> dict[str, int]:
    first, last = month_bounds(start, end)
    log.info("Fetching EUR/NOK %s..%s", first, last)
    by_month: dict[str, list[ExchangeRate]] = defaultdict(list)
    for rate in parse_rates_csv(fetch_rates_csv(first, last)):
        by_month[rate.rate_date[:7]].append(rate)

    written = {
        month: store.write_jsonl(partition_path(month), (r.to_dict() for r in rates))
        for month, rates in sorted(by_month.items())
    }
    log.info("Wrote %d month partitions, %d rows", len(written), sum(written.values()))
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    load_dotenv()
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=today - timedelta(days=31))
    parser.add_argument("--end", type=date.fromisoformat, default=today)
    parser.add_argument("--local-root", default=os.getenv("RAW_LOCAL_ROOT", ""))
    args = parser.parse_args()

    store = RawStore(
        account=os.getenv("AZURE_STORAGE_ACCOUNT"),
        container=os.getenv("AZURE_STORAGE_CONTAINER", "raw"),
        local_root=args.local_root,
    )
    ingest(store, args.start, args.end)


if __name__ == "__main__":
    main()
