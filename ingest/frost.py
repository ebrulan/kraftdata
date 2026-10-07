"""Hourly air temperature from MET Norway's Frost API for one city per bidding zone.

API docs: https://frost.met.no/howto.html
Data license: CC BY 3.0 NO (https://creativecommons.org/licenses/by/3.0/no/), MET Norway.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime

import requests

from ingest.timeutils import oslo_date, oslo_day_bounds_utc

API_URL = "https://frost.met.no/observations/v0.jsonld"


@dataclass(frozen=True)
class Station:
    station_id: str
    city: str
    zone: str


# One long-running station per bidding zone, chosen for complete hourly records since 2022.
STATIONS = [
    Station("SN18700", "Oslo", "NO1"),  # Oslo - Blindern
    Station("SN39040", "Kristiansand", "NO2"),  # Kjevik
    Station("SN68860", "Trondheim", "NO3"),  # Trondheim - Voll
    Station("SN90450", "Tromsø", "NO4"),  # Tromsø
    Station("SN50540", "Bergen", "NO5"),  # Bergen - Florida
]
_BY_ID = {s.station_id: s for s in STATIONS}


@dataclass(frozen=True)
class TemperatureObservation:
    station_id: str
    city: str
    zone: str
    observation_date: str  # calendar day in Norwegian local time, YYYY-MM-DD
    observed_at_utc: str  # ISO 8601, e.g. 2025-03-29T23:00:00+00:00
    air_temperature_c: float
    quality_code: int | None

    def to_dict(self) -> dict:
        return asdict(self)


def fetch_observations_json(client_id: str, start: date, end: date) -> dict:
    """Raw JSON with hourly 2 m air temperature for all stations, [start, end] inclusive.

    Frost caps a response at 100 000 observations; one year for five stations is ~44 000.
    """
    period_start, _ = oslo_day_bounds_utc(start)
    _, period_end = oslo_day_bounds_utc(end)
    params = {
        "sources": ",".join(s.station_id for s in STATIONS),
        "elements": "air_temperature",
        "referencetime": f"{period_start:%Y-%m-%dT%H:%M:%SZ}/{period_end:%Y-%m-%dT%H:%M:%SZ}",
        "timeresolutions": "PT1H",
        "timeoffsets": "PT0H",  # the value at the full hour, not an aggregate
        "levels": "2",  # 2 m above ground (Blindern also measures at 10 m)
    }
    for attempt in range(4):
        response = requests.get(API_URL, params=params, auth=(client_id, ""), timeout=120)
        if response.status_code == 404:  # Frost answers 404 when no data matches
            return {"data": []}
        if response.status_code in (429, 500, 503):
            time.sleep(2**attempt * 5)
            continue
        response.raise_for_status()
        return response.json()
    response.raise_for_status()
    return response.json()


def parse_observations(payload: dict) -> list[TemperatureObservation]:
    """One row per station and hour; unknown stations and duplicate hours are dropped."""
    rows: dict[tuple[str, str], TemperatureObservation] = {}
    for item in payload.get("data", []):
        station = _BY_ID.get(item["sourceId"].split(":")[0])
        if station is None:
            continue
        observed_at = datetime.fromisoformat(item["referenceTime"].replace("Z", "+00:00"))
        observed_at = observed_at.astimezone(UTC)
        for obs in item.get("observations", []):
            if obs.get("elementId") != "air_temperature" or obs.get("value") is None:
                continue
            key = (station.station_id, observed_at.isoformat())
            rows[key] = TemperatureObservation(
                station_id=station.station_id,
                city=station.city,
                zone=station.zone,
                observation_date=oslo_date(observed_at),
                observed_at_utc=observed_at.isoformat(),
                air_temperature_c=float(obs["value"]),
                quality_code=obs.get("qualityCode"),
            )
    return sorted(rows.values(), key=lambda r: (r.station_id, r.observed_at_utc))
