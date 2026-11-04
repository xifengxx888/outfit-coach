"""设置、地点、天气与数据导出接口。

这一层负责把纯解析（`weather.py`）、仓储（`db/repo.py`）和 HTTP 校验接起来。
缓存只存在进程内：预报 15 分钟、失败 60 秒、地理编码 10 分钟；气候落库永久缓存。
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..db.connection import connect
from ..db.repo import (
    PROFILE_FIELDS,
    count_by_status,
    count_locations,
    ensure_profile,
    get_location,
    get_profile,
    insert_location,
    list_locations,
    load_climate,
    profile_height,
    set_default_location,
    upsert_climate,
    upsert_profile,
)
from ..rules import RULE_NAMES
from .export import build_export_zip, db_size, scan_photo_stats
from .weather import (
    WeatherError,
    aggregate_climate,
    climate_uses_apparent,
    climate_window,
    pick_climate,
)

FORECAST_TTL = 15 * 60
FORECAST_FAIL_TTL = 60
GEOCODE_TTL = 10 * 60
VERSION = "0.1.0"

PROFILE_RANGES = {
    "height": (100, 250),
    "weight": (25, 250),
    "shoulder_width": (25, 80),
    "chest": (50, 180),
    "waist": (40, 180),
    "hip": (50, 200),
    "neck": (20, 70),
    "inseam": (30, 130),
    "arm_length": (30, 100),
}
SOURCE_VALUES = Literal["body", "garment", "estimated"]


class WeatherClient(Protocol):
    def geocode(self, query: str) -> list[dict[str, Any]]: ...

    def forecast(self, lat: float, lon: float) -> dict[str, Any]: ...

    def climate(
        self, lat: float, lon: float, start_year: int, end_year: int
    ) -> list[dict[str, Any]]: ...


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    height: int | None = Field(None, ge=100, le=250)
    weight: int | None = Field(None, ge=25, le=250)
    shoulder_width: int | None = Field(None, ge=25, le=80)
    chest: int | None = Field(None, ge=50, le=180)
    waist: int | None = Field(None, ge=40, le=180)
    hip: int | None = Field(None, ge=50, le=200)
    neck: int | None = Field(None, ge=20, le=70)
    inseam: int | None = Field(None, ge=30, le=130)
    arm_length: int | None = Field(None, ge=30, le=100)

    height_source: SOURCE_VALUES | None = None
    weight_source: SOURCE_VALUES | None = None
    shoulder_width_source: SOURCE_VALUES | None = None
    chest_source: SOURCE_VALUES | None = None
    waist_source: SOURCE_VALUES | None = None
    hip_source: SOURCE_VALUES | None = None
    neck_source: SOURCE_VALUES | None = None
    inseam_source: SOURCE_VALUES | None = None
    arm_length_source: SOURCE_VALUES | None = None


class ProfileOut(BaseModel):
    exists: bool
    values: dict[str, int | None]
    sources: dict[str, str | None]
    updated_at: str | None


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("地点名称不能为空")
        return cleaned


class LocationOut(BaseModel):
    id: int
    name: str
    lat: float
    lon: float
    is_default: bool
    climate_ready: bool


def _empty_profile() -> ProfileOut:
    return ProfileOut(
        exists=False,
        values={field: None for field in PROFILE_FIELDS},
        sources={field: None for field in PROFILE_FIELDS},
        updated_at=None,
    )


def _profile_out(conn) -> ProfileOut:
    profile = get_profile(conn)
    if profile is None:
        return _empty_profile()
    return ProfileOut(
        exists=True,
        values={field: profile["values"][field] for field in PROFILE_FIELDS},
        sources={field: profile["sources"][field] for field in PROFILE_FIELDS},
        updated_at=profile["updated_at"],
    )


def _location_out(row: dict[str, Any]) -> LocationOut:
    climate_rows = int(row.get("climate_rows") or 0)
    return LocationOut(
        id=row["id"],
        name=row["name"],
        lat=row["lat"],
        lon=row["lon"],
        is_default=bool(row["is_default"]),
        climate_ready=climate_rows > 0,
    )


def _weather_payload(
    location: dict[str, Any] | None,
    *,
    feels_like: float | None,
    air_temp: float | None = None,
    condition: str = "天气未知",
    weather_code: int | None = None,
    is_rainy: bool = False,
    source: str,
    is_apparent: bool,
    offline: bool,
    climate_ready: bool,
    observed_at: str | None = None,
) -> dict[str, Any]:
    return {
        "location": (
            None
            if location is None
            else {
                "id": location["id"],
                "name": location["name"],
                "is_default": bool(location["is_default"]),
            }
        ),
        "feels_like": feels_like,
        "air_temp": air_temp,
        "condition": condition,
        "weather_code": weather_code,
        "is_rainy": is_rainy,
        "source": source,
        "is_apparent": is_apparent,
        "offline": offline,
        "climate_ready": climate_ready,
        "observed_at": observed_at,
    }


def _fetch_and_store_climate(
    conn,
    weather_client: WeatherClient,
    location_id: int,
    lat: float,
    lon: float,
    today: date,
) -> int:
    """拉十年曲线并落库。只有拿到体感均温才写，避免把均温当体感展示。"""
    start_year, end_year = climate_window(today)
    rows = weather_client.climate(lat, lon, start_year, end_year)
    if not climate_uses_apparent(rows):
        raise WeatherError("气候数据缺少体感温度，稍后可重试")
    values = aggregate_climate(rows)
    if not values:
        raise WeatherError("没有取到气候数据")
    return upsert_climate(conn, location_id, values)


def build_settings_router(
    *,
    db_path: str | Path,
    photo_dir: Path,
    pic_dir: Path,
    weather_client: WeatherClient,
    today_provider=date.today,
) -> APIRouter:
    router = APIRouter()
    forecast_cache: dict[tuple, tuple[float, dict[str, Any]]] = {}
    forecast_failed: dict[tuple, float] = {}
    geocode_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def forecast_key(location: dict[str, Any], day: date) -> tuple:
        return (float(location["lat"]), float(location["lon"]), day.isoformat())

    def cached_forecast(key: tuple) -> dict[str, Any] | None:
        entry = forecast_cache.get(key)
        if entry and time.monotonic() - entry[0] < FORECAST_TTL:
            return entry[1]
        return None

    @router.get("/api/setup")
    def api_setup() -> dict[str, Any]:
        conn = connect(db_path)
        try:
            has_profile = get_profile(conn) is not None
            locations = count_locations(conn)
            item_count = sum(count_by_status(conn).values())
        finally:
            conn.close()
        return {
            "needs_setup": not has_profile and locations == 0,
            "has_profile": has_profile,
            "location_count": locations,
            "item_count": item_count,
        }

    @router.post("/api/setup/skip")
    def api_setup_skip() -> dict[str, bool]:
        conn = connect(db_path)
        try:
            ensure_profile(conn)
            conn.commit()
        finally:
            conn.close()
        return {"needs_setup": False}

    @router.get("/api/profile", response_model=ProfileOut)
    def api_get_profile() -> ProfileOut:
        conn = connect(db_path)
        try:
            return _profile_out(conn)
        finally:
            conn.close()

    @router.put("/api/profile", response_model=ProfileOut)
    def api_put_profile(payload: ProfileIn) -> ProfileOut:
        values = {field: getattr(payload, field) for field in PROFILE_FIELDS}
        sources: dict[str, str | None] = {}
        for field in PROFILE_FIELDS:
            # 空值不保留陈旧来源；非空但没选来源时按「估算」处理
            sources[field] = (
                None
                if values[field] is None
                else (getattr(payload, f"{field}_source") or "estimated")
            )
        conn = connect(db_path)
        try:
            upsert_profile(conn, values, sources)
            conn.commit()
            return _profile_out(conn)
        finally:
            conn.close()

    @router.get("/api/geocode")
    def api_geocode(q: str = Query(..., min_length=1, max_length=60)) -> list[dict]:
        query = q.strip()
        if not query:
            raise HTTPException(status_code=422, detail="请输入地点名称")
        key = query.casefold()
        entry = geocode_cache.get(key)
        if entry and time.monotonic() - entry[0] < GEOCODE_TTL:
            return entry[1]
        try:
            places = weather_client.geocode(query)
        except WeatherError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from None
        geocode_cache[key] = (time.monotonic(), places)
        return places

    @router.get("/api/locations", response_model=list[LocationOut])
    def api_locations() -> list[LocationOut]:
        conn = connect(db_path)
        try:
            return [_location_out(row) for row in list_locations(conn)]
        finally:
            conn.close()

    @router.post("/api/locations", response_model=LocationOut, status_code=201)
    def api_add_location(payload: LocationIn) -> LocationOut:
        today = today_provider()
        conn = connect(db_path)
        try:
            duplicate = conn.execute(
                "SELECT 1 FROM location WHERE name = ?", (payload.name,)
            ).fetchone()
            if duplicate is not None:
                raise HTTPException(status_code=409, detail="这个地点已经加过了")
            location_id = insert_location(
                conn,
                payload.name,
                payload.lat,
                payload.lon,
                is_default=count_locations(conn) == 0,
            )
            conn.commit()
            try:
                _fetch_and_store_climate(
                    conn, weather_client, location_id, payload.lat, payload.lon, today
                )
                conn.commit()
            except WeatherError:
                conn.rollback()
            row = get_location(conn, location_id)
            row = dict(row) if row else {}
            row["climate_rows"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM climate_profile WHERE location_id = ?",
                    (location_id,),
                ).fetchone()[0]
            )
        finally:
            conn.close()
        return _location_out(row)

    @router.post("/api/locations/{location_id}/default", response_model=LocationOut)
    def api_default_location(location_id: int) -> LocationOut:
        conn = connect(db_path)
        try:
            if not set_default_location(conn, location_id):
                raise HTTPException(status_code=404, detail="地点不存在")
            conn.commit()
            row = get_location(conn, location_id)
            row = dict(row) if row else {}
            row["climate_rows"] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM climate_profile WHERE location_id = ?",
                    (location_id,),
                ).fetchone()[0]
            )
        finally:
            conn.close()
        return _location_out(row)

    @router.post("/api/locations/{location_id}/climate")
    def api_refresh_climate(location_id: int) -> dict[str, Any]:
        conn = connect(db_path)
        try:
            location = get_location(conn, location_id)
            if location is None:
                raise HTTPException(status_code=404, detail="地点不存在")
            try:
                days = _fetch_and_store_climate(
                    conn,
                    weather_client,
                    location_id,
                    float(location["lat"]),
                    float(location["lon"]),
                    today_provider(),
                )
                conn.commit()
            except WeatherError as exc:
                conn.rollback()
                raise HTTPException(status_code=502, detail=str(exc)) from None
        finally:
            conn.close()
        return {"location_id": location_id, "days": days, "climate_ready": True}

    @router.get("/api/weather")
    def api_weather(refresh: bool = False) -> dict[str, Any]:
        today = today_provider()
        conn = connect(db_path)
        try:
            locations = list_locations(conn)
            location = next(
                (row for row in locations if row["is_default"]),
                locations[0] if locations else None,
            )
            if location is None:
                return _weather_payload(
                    None, feels_like=None, source="none", is_apparent=False,
                    offline=False, climate_ready=False,
                )
            climate = load_climate(conn, location["id"])
            climate_ready = bool(climate)
        finally:
            conn.close()

        key = forecast_key(location, today)
        cached = None if refresh else cached_forecast(key)
        if cached is not None:
            return _weather_payload(
                location,
                source="forecast",
                offline=False,
                climate_ready=climate_ready,
                **cached,
            )

        failed_until = forecast_failed.get(key)
        if not refresh and failed_until and time.monotonic() < failed_until:
            forecast = None
        else:
            try:
                forecast = weather_client.forecast(
                    float(location["lat"]), float(location["lon"])
                )
            except WeatherError:
                forecast = None
                forecast_failed[key] = time.monotonic() + FORECAST_FAIL_TTL
            else:
                forecast_cache[key] = (time.monotonic(), forecast)
                forecast_failed.pop(key, None)
                return _weather_payload(
                    location,
                    source="forecast",
                    offline=False,
                    climate_ready=climate_ready,
                    **forecast,
                )

        value = pick_climate(climate, today.month, today.day)
        if value is not None:
            return _weather_payload(
                location,
                feels_like=value,
                condition="近十年同期",
                source="climate",
                is_apparent=True,
                offline=True,
                climate_ready=climate_ready,
            )
        return _weather_payload(
            location,
            feels_like=None,
            source="none",
            is_apparent=False,
            offline=True,
            climate_ready=False,
        )

    @router.get("/api/stats")
    def api_stats() -> dict[str, Any]:
        conn = connect(db_path)
        try:
            counts = count_by_status(conn)
            location_count = count_locations(conn)
            profile = get_profile(conn)
            height = profile_height(conn)
        finally:
            conn.close()
        photos = scan_photo_stats([pic_dir, photo_dir])
        return {
            "items": {
                "confirmed": counts.get("confirmed", 0),
                "draft": counts.get("draft", 0),
                "archived": counts.get("archived", 0),
                "total": sum(counts.values()),
            },
            "locations": location_count,
            "photos": photos,
            "db_bytes": db_size(db_path),
            "profile_complete": bool(
                profile and all(value is not None for value in profile["values"].values())
            ),
            "profile_height": height,
            "rules": len(RULE_NAMES),
            "version": VERSION,
        }

    @router.get("/api/export")
    def api_export() -> Response:
        payload = build_export_zip(db_path, pic_dir, photo_dir)
        filename = f"wardrobe-export-{today_provider():%Y%m%d}.zip"
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    return router
