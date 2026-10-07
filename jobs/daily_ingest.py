"""Daily Databricks job task: fetch recent data into the raw volume, then load it into bronze.

Runs on serverless compute, once per source (`--source prices|temperatures|exchange_rates`).
API keys come from the Databricks secret scope `kraftdata`, and raw files are written
through the Unity Catalog volume that points at the ADLS raw container.
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
    parser.add_argument(
        "--source", choices=["prices", "temperatures", "exchange_rates"], required=True
    )
    # Serverless runs the script without __file__, so the bundle passes its file path.
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    args = parser.parse_args()
    repo_root = Path(args.repo_root)
    sys.path.insert(0, str(repo_root))
    from ingest import exchange_rates, prices, temperatures
    from ingest.storage import RawStore

    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=2)
    store = RawStore(local_root=RAW_VOLUME)

    if args.source == "prices":
        # Next-day prices are published around 13:00 CET, so include tomorrow.
        end = date.fromisoformat(args.end) if args.end else today + timedelta(days=1)
        api_key = dbutils.secrets.get(scope="kraftdata", key="entsoe_api_key")
        prices.ingest(api_key, store, start, end)
        sql_file = "bronze_entsoe_prices.sql"
    elif args.source == "temperatures":
        end = date.fromisoformat(args.end) if args.end else today
        client_id = dbutils.secrets.get(scope="kraftdata", key="frost_client_id")
        temperatures.ingest(client_id, store, start, end)
        sql_file = "bronze_frost_temperatures.sql"
    else:
        end = date.fromisoformat(args.end) if args.end else today
        exchange_rates.ingest(store, start, end)
        sql_file = "bronze_norges_bank_eur_nok.sql"

    run_sql_file(
        repo_root / "ingest" / "sql" / sql_file,
        {"start_date": start.isoformat(), "end_date": end.isoformat()},
    )


if __name__ == "__main__":
    main()
