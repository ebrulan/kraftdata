-- Bronze table for Frost hourly air temperature, one row per station and hour.
CREATE TABLE IF NOT EXISTS dbw_kraftdata.bronze.frost_air_temperature (
  station_id STRING COMMENT 'Frost station id, e.g. SN18700',
  city STRING COMMENT 'City the station represents',
  zone STRING COMMENT 'Bidding zone the city belongs to',
  observation_date DATE COMMENT 'Calendar day in Norwegian local time',
  observed_at_utc TIMESTAMP COMMENT 'Observation time (UTC), value at the full hour',
  air_temperature_c DOUBLE COMMENT 'Air temperature 2 m above ground, degrees Celsius',
  quality_code INT COMMENT 'MET quality code, 0 = checked and OK',
  _source_file STRING COMMENT 'Raw file the row was loaded from',
  _loaded_at TIMESTAMP COMMENT 'When the row was loaded into bronze'
)
CLUSTER BY (observation_date)
COMMENT 'MET Norway Frost hourly temperatures (CC BY), loaded from raw/frost/air_temperature';

INSERT INTO dbw_kraftdata.bronze.frost_air_temperature
REPLACE WHERE observation_date BETWEEN :start_date AND :end_date
SELECT
  station_id,
  city,
  zone,
  CAST(observation_date AS DATE),
  CAST(observed_at_utc AS TIMESTAMP),
  air_temperature_c,
  quality_code,
  _metadata.file_path,
  current_timestamp()
FROM read_files(
  '/Volumes/dbw_kraftdata/landing/raw/frost/air_temperature/',
  format => 'json',
  schema => 'station_id STRING, city STRING, zone STRING, observation_date STRING,
             observed_at_utc STRING, air_temperature_c DOUBLE, quality_code INT'
)
WHERE observation_date BETWEEN :start_date AND :end_date;
