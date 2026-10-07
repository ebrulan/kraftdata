import json
from pathlib import Path

from ingest.frost import parse_observations

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parses_one_row_per_station_and_hour():
    rows = parse_observations(load("frost_oslo_bergen_2025-03-30.json"))

    assert len(rows) == 12
    assert {r.city for r in rows} == {"Oslo", "Bergen"}
    oslo = [r for r in rows if r.station_id == "SN18700"]
    assert oslo[0].observed_at_utc == "2025-03-29T23:00:00+00:00"
    assert oslo[0].air_temperature_c == 4.3
    assert oslo[0].zone == "NO1"


def test_observation_date_is_norwegian_local_day():
    rows = parse_observations(load("frost_oslo_bergen_2025-03-30.json"))

    # 23:00 UTC on 29 March is already 00:00 on 30 March in Norway (CET, UTC+1).
    assert rows[0].observation_date == "2025-03-30"


def _item(source: str, time: str, value):
    return {
        "sourceId": source,
        "referenceTime": time,
        "observations": [{"elementId": "air_temperature", "value": value, "qualityCode": 0}],
    }


def test_drops_unknown_stations_missing_values_and_duplicates():
    payload = {
        "data": [
            _item("SN18700:0", "2025-01-01T12:00:00.000Z", -3.0),
            _item("SN18700:0", "2025-01-01T12:00:00.000Z", -3.0),
            _item("SN99999:0", "2025-01-01T12:00:00.000Z", 1.0),
            _item("SN50540:0", "2025-01-01T12:00:00.000Z", None),
        ]
    }

    rows = parse_observations(payload)

    assert [(r.station_id, r.air_temperature_c) for r in rows] == [("SN18700", -3.0)]


def test_empty_payload_gives_no_rows():
    assert parse_observations({"data": []}) == []
