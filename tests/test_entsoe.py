from datetime import date
from pathlib import Path

import pytest

from ingest.entsoe import parse_day_ahead_xml
from ingest.timeutils import date_chunks, oslo_day_bounds_utc

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parses_15_minute_prices_into_96_unique_intervals():
    points = parse_day_ahead_xml(load("entsoe_no1_2026-10-06_pt15m.xml"), "NO1")

    # The response contains two identical TimeSeries; duplicates must be dropped.
    assert len(points) == 96
    assert len({p.interval_start_utc for p in points}) == 96
    assert {p.resolution_minutes for p in points} == {15}
    assert {p.delivery_date for p in points} == {"2026-10-06"}
    assert points[0].interval_start_utc == "2026-10-05T22:00:00+00:00"
    assert points[0].price_eur_mwh == pytest.approx(129.85)


def test_parses_hourly_prices_before_15_minute_switch():
    points = parse_day_ahead_xml(load("entsoe_no1_2022-01-01_pt60m.xml"), "NO1")

    assert {p.resolution_minutes for p in points} == {60}
    first_day = [p for p in points if p.delivery_date == "2022-01-01"]
    assert len(first_day) == 24
    assert first_day[0].interval_start_utc == "2021-12-31T23:00:00+00:00"


A03_WITH_GAP = """<?xml version="1.0" encoding="utf-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries>
    <curveType>A03</curveType>
    <Period>
      <timeInterval><start>2025-03-29T23:00Z</start><end>2025-03-30T03:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>10.5</price.amount></Point>
      <Point><position>3</position><price.amount>12.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>"""


def test_forward_fills_positions_omitted_by_curve_type_a03():
    prices = [p.price_eur_mwh for p in parse_day_ahead_xml(A03_WITH_GAP, "NO2")]

    assert prices == [10.5, 10.5, 12.0, 12.0]


NO_DATA = """<?xml version="1.0" encoding="utf-8"?>
<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">
  <Reason><code>999</code><text>No matching data found for Data item ...</text></Reason>
</Acknowledgement_MarketDocument>"""


def test_no_matching_data_returns_empty_list():
    assert parse_day_ahead_xml(NO_DATA, "NO1") == []


def test_other_acknowledgements_raise():
    with pytest.raises(ValueError):
        parse_day_ahead_xml(NO_DATA.replace("No matching data found", "Invalid token"), "NO1")


@pytest.mark.parametrize(
    ("day", "hours"),
    [(date(2025, 3, 30), 23), (date(2025, 10, 26), 25), (date(2025, 6, 1), 24)],
)
def test_oslo_day_length_follows_daylight_saving_time(day, hours):
    start, end = oslo_day_bounds_utc(day)

    assert (end - start).total_seconds() == hours * 3600


def test_date_chunks_cover_range_without_overlap():
    chunks = date_chunks(date(2022, 1, 1), date(2023, 1, 5), 365)

    assert chunks == [
        (date(2022, 1, 1), date(2022, 12, 31)),
        (date(2023, 1, 1), date(2023, 1, 5)),
    ]
