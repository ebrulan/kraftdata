"""Daily EUR/NOK exchange rates from Norges Bank, used to show prices in øre/kWh.

API docs: https://app.norges-bank.no/query/index.html#/no/
Rates are published on Norwegian business days around 16:00, based on the
ECB concertation at 14:15 CET. Weekends and holidays have no rate.
"""

from __future__ import annotations

import csv
import io
import time
from dataclasses import asdict, dataclass
from datetime import date

import requests

API_URL = "https://data.norges-bank.no/api/data/EXR/B.EUR.NOK.SP"


@dataclass(frozen=True)
class ExchangeRate:
    rate_date: str  # YYYY-MM-DD
    base_currency: str
    quote_currency: str
    rate: float  # units of quote currency per one unit of base currency

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_rates_csv(start: date, end: date) -> str:
    params = {
        "format": "csv",
        "startPeriod": start.isoformat(),
        "endPeriod": end.isoformat(),
        "locale": "en",
    }
    for attempt in range(4):
        response = requests.get(API_URL, params=params, timeout=60)
        if response.status_code == 404:  # no observations in the period
            return ""
        if response.status_code in (429, 500, 503):
            time.sleep(2**attempt * 5)
            continue
        response.raise_for_status()
        return response.text
    response.raise_for_status()
    return response.text


def parse_rates_csv(text: str) -> list[ExchangeRate]:
    if not text.strip():
        return []
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    rates = {}
    for row in reader:
        value = row.get("OBS_VALUE", "").strip()
        if not value:
            continue
        rates[row["TIME_PERIOD"]] = ExchangeRate(
            rate_date=row["TIME_PERIOD"],
            base_currency=row["BASE_CUR"],
            quote_currency=row["QUOTE_CUR"],
            rate=float(value),
        )
    return sorted(rates.values(), key=lambda r: r.rate_date)
