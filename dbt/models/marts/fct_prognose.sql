-- Forecast versus actual next-day average price per zone, in EUR/MWh and øre/kWh.
-- The actual is null until the target day's prices are published.
select
    f.price_area,
    f.forecast_date,
    f.target_date,
    f.split,
    f.forecast_lgbm_eur_mwh,
    f.forecast_naive_eur_mwh,
    a.avg_price_eur_mwh as actual_eur_mwh,
    f.forecast_lgbm_eur_mwh - a.avg_price_eur_mwh as error_lgbm_eur_mwh,
    f.forecast_naive_eur_mwh - a.avg_price_eur_mwh as error_naive_eur_mwh,
    f.forecast_lgbm_eur_mwh * fx.eur_nok / 10 as forecast_lgbm_ore_kwh,
    f.forecast_naive_eur_mwh * fx.eur_nok / 10 as forecast_naive_ore_kwh,
    a.avg_price_ore_kwh as actual_ore_kwh,
    f.mlflow_run_id
from {{ source('ml', 'price_forecasts') }} f
left join {{ ref('fct_spotpris_dag') }} a
    on a.price_area = f.price_area
    and a.delivery_date = f.target_date
left join {{ ref('int_valutakurs_dag') }} fx
    on fx.calendar_date = f.target_date
