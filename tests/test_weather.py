"""天气纯函数单测：窗口、解析、降水码、十年聚合。"""

from __future__ import annotations

from datetime import date

import pytest
from src.api.weather import (
    WeatherError,
    aggregate_climate,
    climate_uses_apparent,
    climate_window,
    is_wet,
    parse_climate,
    parse_forecast,
    parse_geocode,
    pick_climate,
    wmo_text,
)


def test_climate_window_is_previous_ten_years() -> None:
    assert climate_window(date(2026, 10, 26)) == (2016, 2025)
    assert climate_window(date(2026, 1, 1)) == (2016, 2025)


def test_parse_geocode_keeps_duplicates_and_display_name() -> None:
    payload = {
        "results": [
            {
                "name": "朝阳",
                "admin1": "北京",
                "country": "中国",
                "latitude": 39.9,
                "longitude": 116.4,
            },
            {
                "name": "朝阳",
                "admin1": "辽宁",
                "country": "中国",
                "latitude": 41.5,
                "longitude": 120.4,
            },
            {"name": "", "latitude": 1, "longitude": 2},
            {"name": "坏数据", "latitude": "x", "longitude": 2},
        ]
    }
    places = parse_geocode(payload)
    assert len(places) == 2
    assert places[1]["display_name"] == "辽宁 · 中国"
    assert places[0]["lat"] == 39.9


def test_parse_geocode_empty_results_and_bad_shape() -> None:
    assert parse_geocode({}) == []
    with pytest.raises(WeatherError):
        parse_geocode({"results": "oops"})


def test_parse_forecast_prefers_apparent_and_flags_rain() -> None:
    rainy = parse_forecast(
        {
            "current": {
                "temperature_2m": 18.2,
                "apparent_temperature": 16.8,
                "weather_code": 61,
                "time": "2026-10-26T17:00",
            }
        }
    )
    assert rainy == {
        "feels_like": 16.8,
        "air_temp": 18.2,
        "weather_code": 61,
        "condition": "小雨",
        "is_rainy": True,
        "is_apparent": True,
        "observed_at": "2026-10-26T17:00",
    }

    dry = parse_forecast(
        {"current": {"temperature_2m": 20, "weather_code": 3}}
    )
    assert dry["feels_like"] == 20.0
    assert dry["is_apparent"] is False
    assert dry["is_rainy"] is False


def test_parse_forecast_rejects_missing_temperature() -> None:
    with pytest.raises(WeatherError):
        parse_forecast({"current": {"weather_code": 0}})
    with pytest.raises(WeatherError):
        parse_forecast({})


@pytest.mark.parametrize(
    ("code", "expected"),
    [(0, False), (45, False), (3, False), (51, True), (71, True), (95, True), (None, False)],
)
def test_is_wet(code: int | None, expected: bool) -> None:
    assert is_wet(code) is expected


def test_wmo_text_falls_back_for_unknown() -> None:
    assert wmo_text(3) == "阴"
    assert wmo_text(999) == "天气未知"
    assert wmo_text(None) == "天气未知"


def _row(day: date, apparent: float | None, temp: float | None = None) -> dict:
    return {"date": day, "apparent": apparent, "temp": temp}


def test_aggregate_climate_means_same_day_across_years() -> None:
    rows = [
        _row(date(2016, 7, 1), 20.0),
        _row(date(2020, 7, 1), 25.0),
        _row(date(2021, 7, 2), None, 30.0),
        _row(date(2022, 7, 2), 26.0),
    ]
    profile = aggregate_climate(rows)
    assert profile[(7, 1)] == 22.5
    assert profile[(7, 2)] == 26.0
    assert climate_uses_apparent(rows) is True


def test_aggregate_climate_uses_temp_when_no_apparent_at_all() -> None:
    rows = [_row(date(2016, 1, 1), None, 5.0), _row(date(2016, 1, 1), None, 7.0)]
    assert aggregate_climate(rows) == {(1, 1): 6.0}
    assert climate_uses_apparent(rows) is False


def test_aggregate_climate_skips_none_and_keeps_feb_29() -> None:
    rows = [
        _row(date(2020, 2, 29), 10.0),
        _row(date(2024, 2, 29), 14.0),
        _row(date(2021, 2, 28), None),
    ]
    profile = aggregate_climate(rows)
    assert profile[(2, 29)] == 12.0
    assert (2, 28) not in profile


def test_pick_climate_feb_29_falls_back_to_feb_28() -> None:
    profile = {(2, 28): 8.0}
    assert pick_climate(profile, 2, 29) == 8.0
    assert pick_climate(profile, 2, 27) is None
    assert pick_climate({(10, 26): 21.0}, 10, 26) == 21.0


def test_parse_climate_accepts_either_array() -> None:
    rows = parse_climate(
        {
            "daily": {
                "time": ["2016-07-01", "bad-date"],
                "apparent_temperature_mean": [21.5],
                "temperature_2m_mean": [19.0],
            }
        }
    )
    assert len(rows) == 1
    assert rows[0]["apparent"] == 21.5
    assert rows[0]["temp"] == 19.0

    with pytest.raises(WeatherError):
        parse_climate({"daily": {"time": ["2016-07-01"]}})
