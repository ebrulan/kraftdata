from datetime import date

from ingest.exchange_rates import month_bounds
from ingest.norges_bank import parse_rates_csv

HEADER = (
    "FREQ;Frequency;BASE_CUR;Base Currency;QUOTE_CUR;Quote Currency;TENOR;Tenor;DECIMALS;"
    "CALCULATED;UNIT_MULT;Unit Multiplier;COLLECTION;Collection Indicator;TIME_PERIOD;OBS_VALUE"
)


def row(day: str, value: str) -> str:
    return (
        "B;Business;EUR;Euro;NOK;Norwegian krone;SP;Spot;4;false;0;Units;C;"
        f"ECB concertation time 14:15 CET;{day};{value}"
    )


def test_parses_one_rate_per_business_day():
    text = "\n".join([HEADER, row("2026-10-02", "10.8315"), row("2026-10-05", "10.7575")])

    rates = parse_rates_csv(text)

    assert [(r.rate_date, r.rate) for r in rates] == [
        ("2026-10-02", 10.8315),
        ("2026-10-05", 10.7575),
    ]
    assert {(r.base_currency, r.quote_currency) for r in rates} == {("EUR", "NOK")}


def test_skips_rows_without_value_and_empty_responses():
    assert parse_rates_csv("\n".join([HEADER, row("2026-10-02", "")])) == []
    assert parse_rates_csv("") == []


def test_month_bounds_cover_whole_months():
    assert month_bounds(date(2026, 1, 15), date(2026, 2, 3)) == (
        date(2026, 1, 1),
        date(2026, 2, 28),
    )
    assert month_bounds(date(2024, 12, 31), date(2024, 12, 31)) == (
        date(2024, 12, 1),
        date(2024, 12, 31),
    )
