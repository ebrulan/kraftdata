"""Ingest NVE reservoir filling into raw/nve/reservoir_filling/year=YYYY/filling.jsonl.

The API always returns the full history, and NVE can revise recent weeks, so every run
rewrites all years. The data is small, and overwriting whole files keeps it idempotent.

Usage:
    python -m ingest.reservoirs
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict

from dotenv import load_dotenv

from ingest.nve import ReservoirWeek, fetch_reservoir_json, parse_reservoir_json
from ingest.storage import RawStore

log = logging.getLogger(__name__)

SOURCE_PATH = "nve/reservoir_filling"


def partition_path(year: int) -> str:
    return f"{SOURCE_PATH}/year={year}/filling.jsonl"


def ingest(store: RawStore, from_year: int = 2015) -> dict[int, int]:
    log.info("Fetching NVE reservoir statistics")
    by_year: dict[int, list[ReservoirWeek]] = defaultdict(list)
    for week in parse_reservoir_json(fetch_reservoir_json(), from_year):
        by_year[week.iso_year].append(week)

    written = {
        year: store.write_jsonl(partition_path(year), (w.to_dict() for w in weeks))
        for year, weeks in sorted(by_year.items())
    }
    log.info("Wrote %d year partitions, %d rows", len(written), sum(written.values()))
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-year", type=int, default=2015)
    parser.add_argument("--local-root", default=os.getenv("RAW_LOCAL_ROOT", ""))
    args = parser.parse_args()

    store = RawStore(
        account=os.getenv("AZURE_STORAGE_ACCOUNT"),
        container=os.getenv("AZURE_STORAGE_CONTAINER", "raw"),
        local_root=args.local_root,
    )
    ingest(store, args.from_year)


if __name__ == "__main__":
    main()
