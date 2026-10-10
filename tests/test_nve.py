import json
from pathlib import Path

from ingest.nve import parse_reservoir_json

FIXTURES = Path(__file__).parent / "fixtures"


def load() -> list[dict]:
    return json.loads((FIXTURES / "nve_reservoir_2026-w40.json").read_text(encoding="utf-8"))


def test_parses_price_areas_and_publication_date():
    weeks = parse_reservoir_json(load())

    assert weeks, "fixture should contain bidding zones"
    assert all(w.area.startswith("NO") for w in weeks)
    first = weeks[0]
    assert first.week_end_date == "2026-10-04"
    # Week 40 ends on Sunday 4 October and is published on Wednesday 7 October.
    assert first.published_date == "2026-10-07"
    assert 0 <= first.filling_ratio <= 1


def _row(omr_type: str, omrnr: int, year: int, value):
    return {
        "dato_Id": f"{year}-01-07",
        "omrType": omr_type,
        "omrnr": omrnr,
        "iso_aar": year,
        "iso_uke": 1,
        "fyllingsgrad": value,
        "kapasitet_TWh": 10.0,
        "fylling_TWh": 5.0,
    }


def test_skips_watercourse_regions_old_years_and_missing_values():
    rows = [
        _row("EL", 2, 2024, 0.5),
        _row("NO", 0, 2024, 0.6),
        _row("VASS", 1, 2024, 0.7),
        _row("EL", 2, 2010, 0.8),
        _row("EL", 3, 2024, None),
    ]

    weeks = parse_reservoir_json(rows, from_year=2015)

    assert [(w.area_type, w.area) for w in weeks] == [("country", "NO"), ("price_area", "NO2")]
