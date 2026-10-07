-- Bronze table for Norges Bank EUR/NOK rates, one row per business day.
CREATE TABLE IF NOT EXISTS dbw_kraftdata.bronze.norges_bank_eur_nok (
  rate_date DATE COMMENT 'Business day the rate was published',
  base_currency STRING COMMENT 'Always EUR',
  quote_currency STRING COMMENT 'Always NOK',
  rate DOUBLE COMMENT 'NOK per EUR',
  _source_file STRING COMMENT 'Raw file the row was loaded from',
  _loaded_at TIMESTAMP COMMENT 'When the row was loaded into bronze'
)
COMMENT 'Norges Bank daily EUR/NOK exchange rates, loaded from raw/norges_bank/eur_nok';

-- The raw files cover whole months, so widen the window the same way before replacing.
INSERT INTO dbw_kraftdata.bronze.norges_bank_eur_nok
REPLACE WHERE rate_date BETWEEN trunc(CAST(:start_date AS DATE), 'MM')
                            AND last_day(CAST(:end_date AS DATE))
SELECT
  CAST(rate_date AS DATE),
  base_currency,
  quote_currency,
  rate,
  _metadata.file_path,
  current_timestamp()
FROM read_files(
  '/Volumes/dbw_kraftdata/landing/raw/norges_bank/eur_nok/',
  format => 'json',
  schema => 'rate_date STRING, base_currency STRING, quote_currency STRING, rate DOUBLE'
)
WHERE rate_date BETWEEN trunc(CAST(:start_date AS DATE), 'MM')
                    AND last_day(CAST(:end_date AS DATE));
