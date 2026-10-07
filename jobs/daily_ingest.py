"""Daily Databricks job: fetch recent prices into the raw volume, then load them into bronze.

Runs on serverless compute. The ENTSO-E key comes from the Databricks secret scope
`kraftdata`, and raw files are written through the Unity Catalog volume that points
at the ADLS raw container.
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

from databricks.sdk.runtime import dbutils, spark

RAW_VOLUME = "/Volumes/dbw_kraftdata/landing/raw"


def run_sql_file(path: Path, params: dict[str, str]) -> None:
    for statement in path.read_text().split(";"):
        if statement.strip():
            spark.sql(statement, args=params)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("py4j").setLevel(logging.WARNING)
    today = date.today()
    parser = argparse.ArgumentParser()
    # Serverless runs the script without __file__, so the bundle passes its file path.
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    args = parser.parse_args()
    repo_root = Path(args.repo_root)
    sys.path.insert(0, str(repo_root))
    from ingest.prices import ingest
    from ingest.storage import RawStore

    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=2)
    end = date.fromisoformat(args.end) if args.end else today + timedelta(days=1)

    api_key = dbutils.secrets.get(scope="kraftdata", key="entsoe_api_key")
    ingest(api_key, RawStore(local_root=RAW_VOLUME), start, end)
    bronze_sql = repo_root / "ingest" / "sql" / "bronze_entsoe_prices.sql"
    run_sql_file(bronze_sql, {"start_date": start.isoformat(), "end_date": end.isoformat()})


if __name__ == "__main__":
    main()
