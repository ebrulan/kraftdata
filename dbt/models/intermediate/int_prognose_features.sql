{{ config(materialized='table') }}

-- One row per bidding zone and forecast date D: the features a next-day price forecast
-- made on D before the day-ahead auction (12:00 CET) could use, and the price for D+1
-- as the target. Every feature is something already known at that point in time:
--   * prices for D were published on D-1, so D, D-1 and earlier are known;
--   * temperature only for the hours before 10:00 local time on D;
--   * reservoir filling only for weeks NVE had published before D.
with daily as (
    select price_area, delivery_date, avg_price_eur_mwh
    from {{ ref('fct_spotpris_dag') }}
),

prices as (
    select
        price_area,
        delivery_date as forecast_date,
        date_add(delivery_date, 1) as target_date,
        avg_price_eur_mwh as price_today,
        lag(avg_price_eur_mwh, 1) over w as price_yesterday,
        -- D-6 is the same weekday as the target day D+1, one week earlier.
        lag(avg_price_eur_mwh, 6) over w as price_same_weekday_last_week,
        avg(avg_price_eur_mwh) over (
            partition by price_area order by delivery_date rows between 6 preceding and current row
        ) as price_7d_mean,
        lead(avg_price_eur_mwh, 1) over w as target_price_eur_mwh
    from daily
    window w as (partition by price_area order by delivery_date)
),

morning_temperature as (
    select
        price_area,
        delivery_date,
        avg(air_temperature_c) as temperature_morning_c
    from {{ ref('int_pris_vaer_time') }}
    where hour(hour_start_local) < 10
    group by all
),

reservoir as (
    select
        area as price_area,
        published_date,
        filling_ratio,
        -- Compare with the same ISO week in earlier years only, never later ones.
        filling_ratio - avg(filling_ratio) over (
            partition by area, iso_week
            order by iso_year
            range between unbounded preceding and 1 preceding
        ) as filling_vs_earlier_years
    from {{ ref('stg_magasinfylling') }}
    where area_type = 'price_area'
),

reservoir_as_of as (
    select
        p.price_area,
        p.forecast_date,
        r.filling_ratio,
        r.filling_vs_earlier_years,
        row_number() over (
            partition by p.price_area, p.forecast_date order by r.published_date desc
        ) as recency
    from prices p
    join reservoir r
        on r.price_area = p.price_area
        and r.published_date < p.forecast_date
)

select
    p.price_area,
    p.forecast_date,
    p.target_date,
    p.price_today,
    p.price_yesterday,
    p.price_same_weekday_last_week,
    p.price_7d_mean,
    t.temperature_morning_c,
    dayofweek(p.target_date) as target_weekday,  -- 1 = Sunday ... 7 = Saturday
    month(p.target_date) as target_month,
    dayofyear(p.target_date) as target_day_of_year,
    h.holiday_date is not null as target_is_holiday,
    r.filling_ratio as reservoir_filling_ratio,
    r.filling_vs_earlier_years as reservoir_vs_earlier_years,
    p.target_price_eur_mwh
from prices p
left join morning_temperature t
    on t.price_area = p.price_area
    and t.delivery_date = p.forecast_date
left join reservoir_as_of r
    on r.price_area = p.price_area
    and r.forecast_date = p.forecast_date
    and r.recency = 1
left join {{ ref('norwegian_holidays') }} h
    on h.holiday_date = p.target_date
