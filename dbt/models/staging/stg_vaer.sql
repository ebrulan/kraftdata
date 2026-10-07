-- One row per weather station and hour, with explicit UTC and Norwegian local times.
select
    station_id,
    city,
    zone as price_area,
    observation_date,
    observed_at_utc,
    from_utc_timestamp(observed_at_utc, 'Europe/Oslo') as observed_at_local,
    air_temperature_c,
    quality_code
from {{ source('bronze', 'frost_air_temperature') }}
