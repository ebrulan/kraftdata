"""Daily Databricks job task: forecast tomorrow's average price with the champion model.

Runs after dbt has rebuilt `int_prognose_features`. It loads the model version with the
alias "champion" from Unity Catalog, scores the latest forecast date for each trained zone
and upserts the result into `dbw_kraftdata.ml.price_forecasts` as a "live" forecast.
Earlier live forecasts are kept, so the table builds an honest out-of-sample track record.
"""

import argparse

import mlflow
from databricks.sdk.runtime import spark

CATALOG = "dbw_kraftdata"
FEATURES_TABLE = f"{CATALOG}.intermediate.int_prognose_features"
FORECAST_TABLE = f"{CATALOG}.ml.price_forecasts"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", default="NO2")
    parser.add_argument("--model", default=f"{CATALOG}.ml.price_forecast_lgbm")
    args = parser.parse_args()

    mlflow.set_registry_uri("databricks-uc")
    model_uri = f"models:/{args.model}@champion"
    model = mlflow.lightgbm.load_model(model_uri)
    version = mlflow.MlflowClient().get_model_version_by_alias(args.model, "champion")
    features = list(model.feature_name_)

    latest = (
        spark.table(FEATURES_TABLE)
        .where(f"price_area = '{args.zone}' AND target_price_eur_mwh IS NULL")
        .orderBy("forecast_date", ascending=False)
        .limit(1)
        .toPandas()
    )
    if latest.empty:
        print("Nothing to forecast")
        return
    latest["target_is_holiday"] = latest["target_is_holiday"].astype(int)
    forecast = float(model.predict(latest[features])[0])
    row = latest.iloc[0]
    print(f"{args.zone} {row.target_date}: {forecast:.2f} EUR/MWh (model v{version.version})")

    spark.sql(
        f"""
        MERGE INTO {FORECAST_TABLE} t
        USING (SELECT :zone AS price_area, CAST(:forecast_date AS DATE) AS forecast_date,
                      CAST(:target_date AS DATE) AS target_date,
                      CAST(:forecast AS DOUBLE) AS forecast_lgbm_eur_mwh,
                      CAST(:naive AS DOUBLE) AS forecast_naive_eur_mwh,
                      'live' AS split, :run_id AS mlflow_run_id) s
        ON t.price_area = s.price_area AND t.target_date = s.target_date AND t.split = 'live'
        WHEN MATCHED THEN UPDATE SET
          t.forecast_date = s.forecast_date,
          t.forecast_lgbm_eur_mwh = s.forecast_lgbm_eur_mwh,
          t.forecast_naive_eur_mwh = s.forecast_naive_eur_mwh,
          t.mlflow_run_id = s.mlflow_run_id,
          t.created_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT
          (price_area, forecast_date, target_date, forecast_lgbm_eur_mwh,
           forecast_naive_eur_mwh, split, mlflow_run_id, created_at)
          VALUES (s.price_area, s.forecast_date, s.target_date, s.forecast_lgbm_eur_mwh,
                  s.forecast_naive_eur_mwh, s.split, s.mlflow_run_id, current_timestamp())
        """,
        args={
            "zone": args.zone,
            "forecast_date": str(row.forecast_date),
            "target_date": str(row.target_date),
            "forecast": forecast,
            "naive": float(row.price_today),
            "run_id": version.run_id,
        },
    )


if __name__ == "__main__":
    main()
