-- One row per bidding zone and delivery interval, with explicit UTC and Norwegian local times.
-- Timestamps are stored in UTC; local time is derived here once so later models never guess.
select
    zone as price_area,
    delivery_date,
    interval_start_utc,
    interval_start_utc + make_interval(0, 0, 0, 0, 0, resolution_minutes, 0) as interval_end_utc,
    from_utc_timestamp(interval_start_utc, 'Europe/Oslo') as interval_start_local,
    resolution_minutes,
    price_eur_mwh
from {{ source('bronze', 'entsoe_day_ahead_prices') }}
