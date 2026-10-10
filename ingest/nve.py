"""Weekly hydro reservoir filling per bidding zone from NVE's reservoir statistics.

API docs: https://biapi.nve.no/magasinstatistikk/swagger/index.html
Data license: Norwegian Licence for Open Government Data (NLOD), NVE.

A week's value is dated the Sunday that ends the ISO week and is published the following
Wednesday at 13:00 Norwegian time. A forecast must only use values that were published
before it was made, so the publication date is kept as a column.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta

import requests

API_URL = "https://biapi.nve.no/magasinstatistikk/api/Magasinstatistikk/HentOffentligData"

# omrType EL = bidding zone, NO = all of Norway, VASS = watercourse region.
AREA_TYPES = {"EL": "price_area", "NO": "country"}


@dataclass(frozen=True)
class ReservoirWeek:
    area_type: str  # price_area or country
    area: str  # NO1..NO5, or NO for all of Norway
    week_end_date: str  # Sunday ending the ISO week, YYYY-MM-DD
    iso_year: int
    iso_week: int
    published_date: str  # Wednesday after week_end_date
    filling_ratio: float  # 0..1
    filling_twh: float
    capacity_twh: float

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_reservoir_json() -> list[dict]:
    """All published weeks since 1995. The response is small (~15 000 rows)."""
    for attempt in range(4):
        response = requests.get(API_URL, timeout=120)
        if response.status_code in (429, 500, 503):
            time.sleep(2**attempt * 5)
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def parse_reservoir_json(rows: list[dict], from_year: int = 2015) -> list[ReservoirWeek]:
    weeks = {}
    for row in rows:
        area_type = AREA_TYPES.get(row.get("omrType"))
        if area_type is None or row["iso_aar"] < from_year or row.get("fyllingsgrad") is None:
            continue
        area = f"NO{row['omrnr']}" if area_type == "price_area" else "NO"
        week_end = date.fromisoformat(row["dato_Id"][:10])
        week = ReservoirWeek(
            area_type=area_type,
            area=area,
            week_end_date=week_end.isoformat(),
            iso_year=row["iso_aar"],
            iso_week=row["iso_uke"],
            published_date=(week_end + timedelta(days=3)).isoformat(),
            filling_ratio=float(row["fyllingsgrad"]),
            filling_twh=float(row["fylling_TWh"]),
            capacity_twh=float(row["kapasitet_TWh"]),
        )
        weeks[(area, week.week_end_date)] = week
    return sorted(weeks.values(), key=lambda w: (w.area, w.week_end_date))
