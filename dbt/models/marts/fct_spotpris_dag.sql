-- One row per bidding zone and Norwegian market day. A day has 23, 24 or 25 hours
-- depending on daylight saving time, so `hours_in_day` is kept as a column and tested.
select
    price_area,
    delivery_date,
    count(*) as hours_in_day,

    avg(price_eur_mwh) as avg_price_eur_mwh,
    min(price_eur_mwh) as min_price_eur_mwh,
    max(price_eur_mwh) as max_price_eur_mwh,

    avg(price_ore_kwh) as avg_price_ore_kwh,
    min(price_ore_kwh) as min_price_ore_kwh,
    max(price_ore_kwh) as max_price_ore_kwh,

    max_by(hour_start_local, price_eur_mwh) as most_expensive_hour_local,
    min_by(hour_start_local, price_eur_mwh) as cheapest_hour_local,

    avg(air_temperature_c) as avg_temperature_c,
    count(air_temperature_c) as temperature_hours,

    max(eur_nok) as eur_nok
from {{ ref('int_pris_vaer_time') }}
group by all
