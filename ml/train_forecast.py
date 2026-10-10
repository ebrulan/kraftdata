"""Train a LightGBM model for next-day average spot price and compare it with a naive model.

The features come from the dbt model `int_prognose_features` (one row per forecast date D,
target = average price on D+1). Evaluation is time-based: the model is trained on earlier
target dates and tested on later ones, never shuffled, so it is judged the way it would be
used. Everything is logged to MLflow in Databricks, and the forecasts are written to
`dbw_kraftdata.ml.price_forecasts`, which dbt exposes as the mart `fct_prognose`.

Usage:
    uv run --group ml --env-file .env python -m ml.train_forecast
    uv run --group ml --env-file .env python -m ml.train_forecast --zone NO1 --test-start 2025-07-01
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date

import lightgbm as lgb
import mlflow
import pandas as pd
from databricks import sql
from mlflow.models import infer_signature
from sklearn.metrics import mean_absolute_error

log = logging.getLogger(__name__)

CATALOG = "dbw_kraftdata"
FEATURES = [
    "price_today",
    "price_yesterday",
    "price_same_weekday_last_week",
    "price_7d_mean",
    "temperature_morning_c",
    "target_weekday",
    "target_month",
    "target_day_of_year",
    "target_is_holiday",
    "reservoir_filling_ratio",
    "reservoir_vs_earlier_years",
]
TARGET = "target_price_eur_mwh"
PARAMS = {
    "objective": "regression_l1",  # optimise MAE directly; robust to the 2022 price spikes
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "n_estimators": 2000,
    "verbose": -1,
}


def connect():
    return sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"].removeprefix("https://"),
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ["DATABRICKS_TOKEN"],
    )


def load_features(features_table: str, zone: str) -> pd.DataFrame:
    query = f"SELECT * FROM {features_table} WHERE price_area = :zone ORDER BY forecast_date"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(query, {"zone": zone})
        df = cur.fetchall_arrow().to_pandas()
    df["forecast_date"] = pd.to_datetime(df["forecast_date"]).dt.date
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    df["target_is_holiday"] = df["target_is_holiday"].astype(int)
    return df


def time_split(df: pd.DataFrame, test_start: date):
    labelled = df[df[TARGET].notna()]
    train = labelled[labelled["target_date"] < test_start]
    test = labelled[labelled["target_date"] >= test_start]
    # The last 15% of the training period is used for early stopping, again in time order.
    cut = int(len(train) * 0.85)
    return train.iloc[:cut], train.iloc[cut:], test


def fit(train: pd.DataFrame, valid: pd.DataFrame, n_estimators: int | None = None):
    params = dict(PARAMS, n_estimators=n_estimators or PARAMS["n_estimators"])
    model = lgb.LGBMRegressor(**params)
    callbacks = [] if n_estimators else [lgb.early_stopping(100, verbose=False)]
    eval_set = None if n_estimators else [(valid[FEATURES], valid[TARGET])]
    model.fit(train[FEATURES], train[TARGET], eval_set=eval_set, callbacks=callbacks)
    return model


def write_forecasts(rows: pd.DataFrame, zone: str, run_id: str) -> None:
    """Replace this zone's backtest in dbw_kraftdata.ml.price_forecasts.

    Live forecasts from earlier days are kept: they are the only truly out-of-sample
    track record, so only a live row for the same target date is replaced.
    """
    table = f"{CATALOG}.ml.price_forecasts"
    # All values are dates, floats or fixed strings we produce ourselves, so a literal
    # VALUES list is safe here; it is far faster than one INSERT per row.
    values = ",\n".join(
        f"('{zone}', DATE'{r.forecast_date}', DATE'{r.target_date}', "
        f"{float(r.forecast_lgbm)}, {float(r.forecast_naive)}, '{r.split}', '{run_id}')"
        for r in rows.itertuples()
    )
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS {table} (
                price_area STRING, forecast_date DATE, target_date DATE,
                forecast_lgbm_eur_mwh DOUBLE, forecast_naive_eur_mwh DOUBLE,
                split STRING COMMENT 'test = backtest on held-out dates, live = next day',
                mlflow_run_id STRING, created_at TIMESTAMP)
            COMMENT 'Next-day average price forecasts written by ml/train_forecast.py'"""
        )
        live_dates = (
            ", ".join(f"DATE'{d}'" for d in rows.loc[rows.split == "live", "target_date"]) or "NULL"
        )
        cur.execute(
            f"""DELETE FROM {table} WHERE price_area = :zone
                AND (split = 'test' OR target_date IN ({live_dates}))""",
            {"zone": zone},
        )
        cur.execute(
            f"""INSERT INTO {table}
            SELECT *, current_timestamp() FROM VALUES {values}
            AS t(price_area, forecast_date, target_date, forecast_lgbm_eur_mwh,
                 forecast_naive_eur_mwh, split, mlflow_run_id)"""
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for noisy in ("azure", "databricks", "urllib3", "mlflow"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", default="NO2")
    parser.add_argument("--test-start", type=date.fromisoformat, default=date(2025, 1, 1))
    parser.add_argument("--features-table", default=f"{CATALOG}.intermediate.int_prognose_features")
    parser.add_argument("--experiment", default="/Shared/kraftdata-price-forecast")
    parser.add_argument("--register-as", default=f"{CATALOG}.ml.price_forecast_lgbm")
    args = parser.parse_args()

    df = load_features(args.features_table, args.zone)
    train, valid, test = time_split(df, args.test_start)
    log.info("Train %d, valid %d, test %d rows", len(train), len(valid), len(test))

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(args.experiment)

    with mlflow.start_run(run_name=f"lgbm-{args.zone}") as run:
        model = fit(train, valid)
        best_iteration = model.best_iteration_ or PARAMS["n_estimators"]

        pred_lgbm = model.predict(test[FEATURES])
        pred_naive = test["price_today"]  # naive model: tomorrow = today
        mae_lgbm = mean_absolute_error(test[TARGET], pred_lgbm)
        mae_naive = mean_absolute_error(test[TARGET], pred_naive)
        skill = 1 - mae_lgbm / mae_naive
        log.info("MAE LightGBM %.2f, naive %.2f, skill %.1f%%", mae_lgbm, mae_naive, skill * 100)

        mlflow.log_params(
            {
                **{k: v for k, v in PARAMS.items() if k != "n_estimators"},
                "best_iteration": best_iteration,
                "zone": args.zone,
                "test_start": args.test_start.isoformat(),
                "features": ",".join(FEATURES),
                "train_rows": len(train) + len(valid),
                "test_rows": len(test),
            }
        )
        mlflow.log_metrics({"mae_lgbm": mae_lgbm, "mae_naive": mae_naive, "skill_vs_naive": skill})
        importance = pd.DataFrame(
            {"feature": FEATURES, "gain": model.booster_.feature_importance("gain")}
        ).sort_values("gain", ascending=False)
        mlflow.log_table(importance, "feature_importance.json")
        log.info("Feature importance (gain):\n%s", importance.to_string(index=False))

        # Refit on all labelled data with the tuned number of trees for the live forecast.
        labelled = pd.concat([train, valid, test])
        final = fit(labelled, labelled, n_estimators=best_iteration)
        latest = df[df[TARGET].isna()].tail(1)
        model_info = mlflow.lightgbm.log_model(
            final,
            name="model",
            signature=infer_signature(labelled[FEATURES], final.predict(labelled[FEATURES])),
            input_example=labelled[FEATURES].head(3),
            registered_model_name=args.register_as,
        )
        # The daily job scores with whichever version carries the "champion" alias.
        mlflow.MlflowClient().set_registered_model_alias(
            args.register_as, "champion", model_info.registered_model_version
        )

        backtest = test[["forecast_date", "target_date"]].assign(
            forecast_lgbm=pred_lgbm, forecast_naive=pred_naive.values, split="test"
        )
        live = latest[["forecast_date", "target_date"]].assign(
            forecast_lgbm=final.predict(latest[FEATURES]),
            forecast_naive=latest["price_today"].values,
            split="live",
        )
        write_forecasts(pd.concat([backtest, live]), args.zone, run.info.run_id)
        if not live.empty:
            log.info(
                "Forecast for %s: %.2f EUR/MWh",
                live.target_date.iloc[0],
                live.forecast_lgbm.iloc[0],
            )


if __name__ == "__main__":
    main()
