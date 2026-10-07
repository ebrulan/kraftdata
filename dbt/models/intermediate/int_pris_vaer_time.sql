{{ config(materialized='table') }}

-- One row per bidding zone and hour: average price, price in øre/kWh and the temperature
-- in the zone's reference city. Since October 2025 a day-ahead hour has four 15-minute
-- prices; they are averaged so prices line up with the hourly temperature observations.
with price_hourly as (
    select
        price_area,
        delivery_date,
        date_trunc('HOUR', interval_start_utc) as hour_start_utc,
        avg(price_eur_mwh) as price_eur_mwh,
        count(*) as price_intervals
    from {{ ref('stg_spotpriser') }}
    group by all
)

select
    p.price_area,
    p.delivery_date,
    p.hour_start_utc,
    from_utc_timestamp(p.hour_start_utc, 'Europe/Oslo') as hour_start_local,
    p.price_eur_mwh,
    -- EUR/MWh * NOK/EUR = NOK/MWh; / 1000 = NOK/kWh; * 100 = øre/kWh. Excluding VAT and fees.
    p.price_eur_mwh * fx.eur_nok / 10 as price_ore_kwh,
    fx.eur_nok,
    w.air_temperature_c,
    p.price_intervals
from price_hourly p
left join {{ ref('int_valutakurs_dag') }} fx
    on fx.calendar_date = p.delivery_date
left join {{ ref('stg_vaer') }} w
    on w.price_area = p.price_area
    and w.observed_at_utc = p.hour_start_utc
