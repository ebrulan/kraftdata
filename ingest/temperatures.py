"""Ingest Frost hourly temperatures into raw/frost/air_temperature/date=YYYY-MM-DD/.

Usage:
    python -m ingest.temperatures --start 2022-01-01 --end 2022-12-31
    python -m ingest.temperatures                      # the last three days
    python -m ingest.temperatures --local-root data/raw  # write locally instead of ADLS
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import defaultdict
from datetime import date, timedelta

from dotenv import load_dotenv

from ingest.frost import TemperatureObservation, fetch_observations_json, parse_observations
from ingest.storage import RawStore
from ingest.timeutils import date_chunks

log = logging.getLogger(__name__)

SOURCE_PATH = "frost/air_temperature"
MAX_DAYS_PER_REQUEST = 366


def partition_path(observation_date: str) -> str:
    return f"{SOURCE_PATH}/date={observation_date}/observations.jsonl"


def ingest(client_id: str, store: RawStore, start: date, end: date) -> dict[str, int]:
    """Fetch all stations for [start, end] and write one file per Norwegian calendar day."""
    by_date: dict[str, list[TemperatureObservation]] = defaultdict(list)
    for chunk_start, chunk_end in date_chunks(start, end, MAX_DAYS_PER_REQUEST):
        log.info("Fetching temperatures %s..%s", chunk_start, chunk_end)
        for row in parse_observations(fetch_observations_json(client_id, chunk_start, chunk_end)):
            if start.isoformat() <= row.observation_date <= end.isoformat():
                by_date[row.observation_date].append(row)

    written = {}
    for observation_date, rows in sorted(by_date.items()):
        written[observation_date] = store.write_jsonl(
            partition_path(observation_date), (r.to_dict() for r in rows)
        )
    log.info("Wrote %d date partitions, %d rows", len(written), sum(written.values()))
    return written


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("azure").setLevel(logging.WARNING)
    load_dotenv()
    today = date.today()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=today - timedelta(days=2))
    parser.add_argument("--end", type=date.fromisoformat, default=today)
    parser.add_argument("--local-root", default=os.getenv("RAW_LOCAL_ROOT", ""))
    args = parser.parse_args()

    store = RawStore(
        account=os.getenv("AZURE_STORAGE_ACCOUNT"),
        container=os.getenv("AZURE_STORAGE_CONTAINER", "raw"),
        local_root=args.local_root,
    )
    ingest(os.environ["FROST_CLIENT_ID"], store, args.start, args.end)


if __name__ == "__main__":
    main()
