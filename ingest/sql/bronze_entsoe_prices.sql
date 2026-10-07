-- Bronze table for ENTSO-E day-ahead prices: the raw JSONL rows as a Delta table,
-- with light typing and lineage columns. Business logic belongs in dbt, not here.
CREATE TABLE IF NOT EXISTS dbw_kraftdata.bronze.entsoe_day_ahead_prices (
  zone STRING COMMENT 'Bidding zone, NO1-NO5',
  delivery_date DATE COMMENT 'Market day in Norwegian local time',
  interval_start_utc TIMESTAMP COMMENT 'Start of the delivery interval (UTC)',
  resolution_minutes INT COMMENT '60 before October 2025, 15 after',
  price_eur_mwh DOUBLE COMMENT 'Day-ahead price in EUR/MWh',
  _source_file STRING COMMENT 'Raw file the row was loaded from',
  _loaded_at TIMESTAMP COMMENT 'When the row was loaded into bronze'
)
CLUSTER BY (delivery_date)
COMMENT 'ENTSO-E day-ahead prices, loaded from raw/entsoe/day_ahead_prices';

-- Idempotent load: REPLACE WHERE swaps out exactly the requested dates, so
-- re-loading a date replaces its rows instead of duplicating them.
INSERT INTO dbw_kraftdata.bronze.entsoe_day_ahead_prices
REPLACE WHERE delivery_date BETWEEN :start_date AND :end_date
SELECT
  zone,
  CAST(delivery_date AS DATE),
  CAST(interval_start_utc AS TIMESTAMP),
  resolution_minutes,
  price_eur_mwh,
  _metadata.file_path,
  current_timestamp()
FROM read_files(
  '/Volumes/dbw_kraftdata/landing/raw/entsoe/day_ahead_prices/',
  format => 'json',
  schema => 'zone STRING, delivery_date STRING, interval_start_utc STRING,
             resolution_minutes INT, price_eur_mwh DOUBLE'
)
WHERE delivery_date BETWEEN :start_date AND :end_date;
