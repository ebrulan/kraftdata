-- Bronze table for NVE weekly reservoir filling. The raw files hold the full history and
-- NVE may revise recent weeks, so the table is rebuilt from all files on every load.
CREATE OR REPLACE TABLE dbw_kraftdata.bronze.nve_reservoir_filling
COMMENT 'NVE weekly hydro reservoir filling per bidding zone and for Norway, loaded from raw/nve/reservoir_filling'
AS
SELECT
  area_type,
  area,
  CAST(week_end_date AS DATE) AS week_end_date,
  iso_year,
  iso_week,
  CAST(published_date AS DATE) AS published_date,
  filling_ratio,
  filling_twh,
  capacity_twh,
  _metadata.file_path AS _source_file,
  current_timestamp() AS _loaded_at
FROM read_files(
  '/Volumes/dbw_kraftdata/landing/raw/nve/reservoir_filling/',
  format => 'json',
  schema => 'area_type STRING, area STRING, week_end_date STRING, iso_year INT, iso_week INT,
             published_date STRING, filling_ratio DOUBLE, filling_twh DOUBLE, capacity_twh DOUBLE'
);
