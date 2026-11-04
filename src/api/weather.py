"""Open-Meteo 接入：地理编码、实时天气、十年气候。

这一层只做「网络 + 解析」，不碰数据库。解析函数是纯函数，方便单测；
对外抛出的 `WeatherError` 只带安全中文文案，不暴露上游 URL、响应体或堆栈。
"""

from __future__ import annotations

import json
import math
from datetime import date
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
DEFAULT_TIMEOUT = 10.0
USER_AGENT = "wardrobe-local/0.1 (personal use)"

_UPSTREAM_DOWN = "天气服务暂时不可用"
_UPSTREAM_BAD = "天气服务返回了无法识别的数据"

WET_CODES = frozenset(
    {
        51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
        71, 73, 75, 77, 80, 81, 82, 85, 86, 95, 96, 99,
    }
)

_WMO_TEXT = {
    0: "晴",
    1: "大部晴朗",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    56: "冻毛毛雨",
    57: "冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷雨",
    96: "雷雨伴冰雹",
    99: "雷雨伴冰雹",
}


class WeatherError(ValueError):
    """天气服务不可用。消息可以直接给用户看。"""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def wmo_text(code: int | None) -> str:
    if code is None:
        return "天气未知"
    return _WMO_TEXT.get(code, "天气未知")


def is_wet(code: int | None) -> bool:
    """雨、雪、阵雨、雷雨都算湿；雾与阴天不算。"""
    return code in WET_CODES


def climate_window(today: date) -> tuple[int, int]:
    """近十年窗口：去年往前数十年，含首尾。"""
    return today.year - 10, today.year - 1


def parse_geocode(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise WeatherError(_UPSTREAM_BAD)
    results = payload.get("results")
    if results is None:
        return []
    if not isinstance(results, list):
        raise WeatherError(_UPSTREAM_BAD)

    places: list[dict[str, Any]] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        lat = _number(raw.get("latitude"))
        lon = _number(raw.get("longitude"))
        if not isinstance(name, str) or not name.strip() or lat is None or lon is None:
            continue
        admin1 = raw.get("admin1") if isinstance(raw.get("admin1"), str) else ""
        country = raw.get("country") if isinstance(raw.get("country"), str) else ""
        display = " · ".join(part for part in (admin1, country) if part)
        places.append(
            {
                "name": name.strip(),
                "admin1": admin1,
                "country": country,
                "display_name": display or name.strip(),
                "lat": lat,
                "lon": lon,
            }
        )
    return places


def parse_forecast(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WeatherError(_UPSTREAM_BAD)
    current = payload.get("current")
    if not isinstance(current, dict):
        raise WeatherError(_UPSTREAM_BAD)

    air_temp = _number(current.get("temperature_2m"))
    apparent = _number(current.get("apparent_temperature"))
    feels_like = apparent if apparent is not None else air_temp
    if feels_like is None:
        raise WeatherError(_UPSTREAM_BAD)

    code = _integer(current.get("weather_code"))
    observed_at = current.get("time")
    return {
        "feels_like": round(feels_like, 1),
        "air_temp": round(air_temp, 1) if air_temp is not None else None,
        "weather_code": code,
        "condition": wmo_text(code),
        "is_rainy": is_wet(code),
        "is_apparent": apparent is not None,
        "observed_at": observed_at if isinstance(observed_at, str) else None,
    }


def parse_climate(payload: Any) -> list[dict[str, Any]]:
    """把 Archive 的逐日数组摊平成行；缺失值保留 None。"""
    if not isinstance(payload, dict):
        raise WeatherError(_UPSTREAM_BAD)
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise WeatherError(_UPSTREAM_BAD)

    times = daily.get("time")
    apparent = daily.get("apparent_temperature_mean")
    temp = daily.get("temperature_2m_mean")
    if not isinstance(times, list):
        raise WeatherError(_UPSTREAM_BAD)
    if apparent is not None and not isinstance(apparent, list):
        raise WeatherError(_UPSTREAM_BAD)
    if temp is not None and not isinstance(temp, list):
        raise WeatherError(_UPSTREAM_BAD)
    if apparent is None and temp is None:
        raise WeatherError(_UPSTREAM_BAD)

    def value_at(values: Any, index: int) -> float | None:
        if not isinstance(values, list) or index >= len(values):
            return None
        return _number(values[index])

    rows: list[dict[str, Any]] = []
    for index, raw_day in enumerate(times):
        if not isinstance(raw_day, str):
            continue
        try:
            day = date.fromisoformat(raw_day)
        except ValueError:
            continue
        rows.append(
            {
                "date": day,
                "apparent": value_at(apparent, index),
                "temp": value_at(temp, index),
            }
        )
    if not rows:
        raise WeatherError(_UPSTREAM_BAD)
    return rows


def climate_uses_apparent(rows: list[dict[str, Any]]) -> bool:
    """只要有任何一天有体感值，整条曲线就统一用体感，避免单位混用。"""
    return any(row["apparent"] is not None for row in rows)


def aggregate_climate(rows: list[dict[str, Any]]) -> dict[tuple[int, int], float]:
    """按「月-日」跨年求均值，跳过 None。2/29 有几条算几条。"""
    use_apparent = climate_uses_apparent(rows)
    buckets: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        value = row["apparent"] if use_apparent else row["temp"]
        if value is None:
            continue
        key = (row["date"].month, row["date"].day)
        buckets.setdefault(key, []).append(value)
    return {
        key: round(sum(values) / len(values), 1)
        for key, values in buckets.items()
        if values
    }


def pick_climate(
    profile: dict[tuple[int, int], float], month: int, day: int
) -> float | None:
    value = profile.get((month, day))
    if value is not None:
        return value
    if (month, day) == (2, 29):
        return profile.get((2, 28))
    return None


class OpenMeteoClient:
    """真实网络客户端。测试通过 `create_app(weather_client=...)` 注入假实现。"""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{url}?{urlencode(params)}", headers={"User-Agent": USER_AGENT}
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError):
            raise WeatherError(_UPSTREAM_DOWN) from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise WeatherError(_UPSTREAM_BAD)
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise WeatherError(_UPSTREAM_BAD) from None
        if not isinstance(payload, dict):
            raise WeatherError(_UPSTREAM_BAD)
        return payload

    def geocode(self, query: str) -> list[dict[str, Any]]:
        payload = self._get(
            GEOCODE_URL,
            {"name": query, "count": 8, "language": "zh", "format": "json"},
        )
        return parse_geocode(payload)

    def forecast(self, lat: float, lon: float) -> dict[str, Any]:
        payload = self._get(
            FORECAST_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code",
                "timezone": "auto",
            },
        )
        return parse_forecast(payload)

    def climate(self, lat: float, lon: float, start_year: int, end_year: int) -> list[dict[str, Any]]:
        payload = self._get(
            ARCHIVE_URL,
            {
                "latitude": lat,
                "longitude": lon,
                "start_date": f"{start_year}-01-01",
                "end_date": f"{end_year}-12-31",
                "daily": "apparent_temperature_mean,temperature_2m_mean",
                "timezone": "auto",
            },
        )
        return parse_climate(payload)
