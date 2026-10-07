"""Day-ahead spot prices for the Norwegian bidding zones from the ENTSO-E Transparency Platform.

API docs: https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API_URL = "https://web-api.tp.entsoe.eu/api"
OSLO = ZoneInfo("Europe/Oslo")

# EIC area codes for the Norwegian bidding zones.
ZONES = {
    "NO1": "10YNO-1--------2",
    "NO2": "10YNO-2--------T",
    "NO3": "10YNO-3--------J",
    "NO4": "10YNO-4--------9",
    "NO5": "10Y1001A1001A48H",
}

_RESOLUTION = re.compile(r"PT(\d+)M")


@dataclass(frozen=True)
class PricePoint:
    zone: str
    delivery_date: str  # market day in Norwegian local time, YYYY-MM-DD
    interval_start_utc: str  # ISO 8601, e.g. 2026-10-05T22:00:00+00:00
    resolution_minutes: int
    price_eur_mwh: float

    def to_dict(self) -> dict:
        return asdict(self)


def oslo_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """Start and end of a Norwegian calendar day in UTC (23, 24 or 25 hours long)."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=OSLO)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=OSLO)
    return start.astimezone(UTC), end.astimezone(UTC)


def fetch_day_ahead_xml(api_key: str, zone: str, start: date, end: date) -> str:
    """Raw XML for all delivery days from `start` up to and including `end`.

    ENTSO-E accepts at most one year per request, so callers should chunk long ranges.
    """
    period_start, _ = oslo_day_bounds_utc(start)
    _, period_end = oslo_day_bounds_utc(end)
    params = {
        "securityToken": api_key,
        "documentType": "A44",  # price document
        "in_Domain": ZONES[zone],
        "out_Domain": ZONES[zone],
        "periodStart": period_start.strftime("%Y%m%d%H%M"),
        "periodEnd": period_end.strftime("%Y%m%d%H%M"),
    }
    for attempt in range(4):
        response = requests.get(API_URL, params=params, timeout=120)
        if response.status_code in (429, 503):
            time.sleep(2**attempt * 5)
            continue
        response.raise_for_status()
        return response.text
    response.raise_for_status()
    return response.text


def parse_day_ahead_xml(xml_text: str, zone: str) -> list[PricePoint]:
    """Parse an A44 price document into one row per delivery interval.

    Handles three quirks of the API:
      - resolution is PT60M until February 2025 and PT15M after that. From
        February to September 2025 the 15-minute points just repeat the hourly
        price; real 15-minute prices start with delivery day 1 October 2025;
      - curve type A03 omits a point when the price equals the previous point,
        so gaps must be forward-filled;
      - the same period can appear in several TimeSeries, so rows are de-duplicated.
    """
    root = ET.fromstring(xml_text)
    ns = {"n": root.tag.split("}")[0].strip("{")}

    if root.tag.endswith("Acknowledgement_MarketDocument"):
        reason = root.findtext(".//n:Reason/n:text", default="", namespaces=ns)
        if "No matching data" in reason:
            return []
        raise ValueError(f"ENTSO-E returned an error: {reason}")

    points: dict[str, PricePoint] = {}
    for period in root.iterfind(".//n:TimeSeries/n:Period", ns):
        start = _parse_utc(period.findtext("n:timeInterval/n:start", namespaces=ns))
        end = _parse_utc(period.findtext("n:timeInterval/n:end", namespaces=ns))
        resolution = _parse_resolution(period.findtext("n:resolution", namespaces=ns))
        step = timedelta(minutes=resolution)
        n_slots = int((end - start) / step)

        prices_by_position = {
            int(p.findtext("n:position", namespaces=ns)): float(
                p.findtext("n:price.amount", namespaces=ns)
            )
            for p in period.iterfind("n:Point", ns)
        }

        price = None
        for position in range(1, n_slots + 1):
            price = prices_by_position.get(position, price)
            if price is None:
                continue
            interval_start = start + (position - 1) * step
            key = interval_start.isoformat()
            points[key] = PricePoint(
                zone=zone,
                delivery_date=interval_start.astimezone(OSLO).date().isoformat(),
                interval_start_utc=key,
                resolution_minutes=resolution,
                price_eur_mwh=price,
            )

    return sorted(points.values(), key=lambda p: p.interval_start_utc)


def _parse_utc(value: str | None) -> datetime:
    if value is None:
        raise ValueError("Missing timeInterval in price document")
    return datetime.strptime(value, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def _parse_resolution(value: str | None) -> int:
    match = _RESOLUTION.fullmatch(value or "")
    if not match:
        raise ValueError(f"Unsupported resolution: {value}")
    return int(match.group(1))
