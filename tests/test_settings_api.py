"""设置 / 地点 / 天气 / 统计 / 导出接口单测。全部使用假天气客户端。"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sqlite3
import zipfile
from datetime import date
from pathlib import Path

import pytest
from factories import layer_item
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.settings_routes import build_settings_router
from src.api.weather import WeatherError
from src.db.connection import connect, open_db
from src.db.repo import insert_item

TODAY = date(2026, 10, 26)


class FakeWeather:
    def __init__(self) -> None:
        self.geocode_results: list[dict] = []
        self.forecast_result: dict = {
            "feels_like": 27.4,
            "air_temp": 26.1,
            "condition": "多云",
            "weather_code": 3,
            "is_rainy": False,
            "is_apparent": True,
            "observed_at": "2026-10-26T17:00",
        }
        self.climate_rows: list[dict] = _climate_rows()
        self.fail_geocode = False
        self.fail_forecast = False
        self.fail_climate = False
        self.calls = {"geocode": 0, "forecast": 0, "climate": 0}
        self.forecast_coords: list[tuple[float, float]] = []

    def geocode(self, query: str) -> list[dict]:
        self.calls["geocode"] += 1
        if self.fail_geocode:
            raise WeatherError("天气服务暂时不可用")
        return list(self.geocode_results)

    def forecast(self, lat: float, lon: float) -> dict:
        self.calls["forecast"] += 1
        self.forecast_coords.append((lat, lon))
        if self.fail_forecast:
            raise WeatherError("天气服务暂时不可用")
        return dict(self.forecast_result)

    def climate(self, lat: float, lon: float, start: int, end: int) -> list[dict]:
        self.calls["climate"] += 1
        if self.fail_climate:
            raise WeatherError("天气服务暂时不可用")
        return list(self.climate_rows)


def _climate_rows(month: int = 10, day: int = 26) -> list[dict]:
    """十年 × 10 天。每天均值相同，方便断言；包含 10/26。"""
    days = [22, 23, 24, 25, 26, 27, 28, 29, 30, 31] if day == 26 else [day]
    return [
        {"date": date(year, month, d), "apparent": 20.0 + (year - 2016), "temp": None}
        for year in range(2016, 2026)
        for d in days
    ]


def _seed(db: Path, items: list) -> None:
    conn = connect(db)
    try:
        for item in items:
            insert_item(conn, item)
        conn.commit()
    finally:
        conn.close()


def _router_client(tmp_path: Path, fake: FakeWeather) -> tuple[TestClient, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    db = tmp_path / "wardrobe.db"
    open_db(db).close()
    pic = tmp_path / "pic"
    photos = tmp_path / "photos"
    pic.mkdir(exist_ok=True)
    photos.mkdir(exist_ok=True)
    app = FastAPI()
    app.include_router(
        build_settings_router(
            db_path=db,
            photo_dir=photos,
            pic_dir=pic,
            weather_client=fake,
            today_provider=lambda: TODAY,
        )
    )
    return TestClient(app), db


def _app_client(
    tmp_path: Path, fake: FakeWeather, items: list
) -> tuple[TestClient, Path]:
    db = tmp_path / "wardrobe.db"
    open_db(db).close()
    _seed(db, items)
    pic = tmp_path / "pic"
    photos = tmp_path / "photos"
    pic.mkdir(exist_ok=True)
    photos.mkdir(exist_ok=True)
    client = TestClient(
        create_app(db, photo_dir=photos, weather_client=fake, pic_dir=pic)
    )
    return client, db


# ---------------------------------------------------------------------------
# 首次设置与身材
# ---------------------------------------------------------------------------


def test_fresh_database_needs_setup(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    assert client.get("/api/setup").json() == {
        "needs_setup": True,
        "has_profile": False,
        "location_count": 0,
        "item_count": 0,
    }


def test_skip_is_idempotent_and_does_not_overwrite(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    assert client.post("/api/setup/skip").json() == {"needs_setup": False}
    assert client.get("/api/setup").json()["needs_setup"] is False

    body = client.put("/api/profile", json={"height": 175}).json()
    assert body["values"]["height"] == 175
    assert body["sources"]["height"] == "estimated"

    client.post("/api/setup/skip")
    profile = client.get("/api/profile").json()
    assert profile["exists"] is True
    assert profile["values"]["height"] == 175


def test_only_profile_or_only_location_ends_setup(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    client.put("/api/profile", json={"height": 170})
    assert client.get("/api/setup").json()["needs_setup"] is False

    other, _ = _router_client(tmp_path / "other", fake)
    other.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})
    setup = other.get("/api/setup").json()
    assert setup["needs_setup"] is False
    assert setup["has_profile"] is False
    assert setup["location_count"] == 1


def test_profile_empty_shape_and_sources(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    body = client.get("/api/profile").json()
    assert body["exists"] is False
    assert body["updated_at"] is None
    assert set(body["values"]) == {
        "height", "weight", "shoulder_width", "chest", "waist",
        "hip", "neck", "inseam", "arm_length",
    }
    assert all(value is None for value in body["values"].values())
    assert all(value is None for value in body["sources"].values())


@pytest.mark.parametrize(
    "payload",
    [
        {"height": 99},
        {"height": 251},
        {"weight": 24},
        {"arm_length": 101},
        {"height": "tall"},
        {"height_source": "vlm"},
        {"unknown": 1},
    ],
)
def test_profile_rejects_bad_payload(tmp_path, payload) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    assert client.put("/api/profile", json=payload).status_code == 422


def test_profile_put_is_full_replace_and_clears_source(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    client.put(
        "/api/profile",
        json={"height": 175, "height_source": "body", "weight": 70},
    )
    body = client.put("/api/profile", json={"waist": 82}).json()
    assert body["values"]["height"] is None
    assert body["sources"]["height"] is None
    assert body["values"]["weight"] is None
    assert body["values"]["waist"] == 82
    assert body["sources"]["waist"] == "estimated"


def test_height_reaches_rule_context_and_rain_flag(tmp_path) -> None:
    items = [
        layer_item("base", id=1),
        layer_item("bottom", id=2),
        layer_item("shoes", id=3),
        layer_item("outer", id=5, length_cm=100),
    ]
    client, _ = _app_client(tmp_path, FakeWeather(), items)
    client.put("/api/profile", json={"height": 165, "height_source": "body"})

    body = client.get(
        "/api/outfits", params={"feels_like": 15, "is_rainy": "true"}
    ).json()
    assert body["context"] == {
        "occasion": "日常",
        "feels_like": 15.0,
        "is_rainy": True,
        "height_cm": 165,
    }
    assert any(
        "R-PRP-04" in outfit["thumbs_down"] for outfit in body["outfits"]
    )


def test_body_measurements_reach_outfits_and_today(tmp_path) -> None:
    """身材五项经 profile 进入求解：合身理由排最前，不合身时改成扣分。"""
    items = [
        layer_item(
            "base", id=1, name="合身T恤",
            shoulder_cm=44.0, chest_width_cm=49.0, sleeve_cm=56.0,
        ),
        layer_item("bottom", id=2, name="合身裤子", hip_cm=47.0),
        layer_item("shoes", id=3),
    ]
    client, _ = _app_client(tmp_path, FakeWeather(), items)
    profile = {
        "height": 165, "shoulder_width": 43, "chest": 91,
        "hip": 91, "arm_length": 53,
        "height_source": "body", "shoulder_width_source": "body",
        "chest_source": "body", "hip_source": "body", "arm_length_source": "body",
    }
    client.put("/api/profile", json=profile)

    body = client.get("/api/outfits", params={"feels_like": 20}).json()
    first = body["outfits"][0]
    bullets = first["reason"].split("；")
    assert len(bullets) <= 5
    assert bullets[0].startswith("上装合身")
    assert bullets[1].startswith("下装合身")
    assert {"R-SIZ-01", "R-SIZ-02"} <= set(first["thumbs_up"])
    assert not {"R-SIZ-01", "R-SIZ-02"} & set(first["thumbs_down"])
    fitting_score = first["score"]

    today = client.get("/api/today", params={"feels_like": 20}).json()
    today_rules = set(today["outfits"][0]["thumbs_up"]) | set(
        today["outfits"][0]["thumbs_down"]
    )
    assert {"R-SIZ-01", "R-SIZ-02"} <= today_rules

    # 肩宽改大 7cm：同一件 T 恤变成肩线窄 6cm，扣分并写进 thumbs_down
    client.put("/api/profile", json={**profile, "shoulder_width": 50})
    tighter = client.get("/api/outfits", params={"feels_like": 20}).json()["outfits"][0]
    assert tighter["score"] < fitting_score
    assert "R-SIZ-01" in tighter["thumbs_down"]
    assert "肩线窄" in tighter["reason"]


# ---------------------------------------------------------------------------
# 地理编码与地点
# ---------------------------------------------------------------------------


def test_geocode_returns_candidates_and_caches(tmp_path) -> None:
    fake = FakeWeather()
    fake.geocode_results = [
        {"name": "深圳", "admin1": "广东", "country": "中国",
         "display_name": "广东 · 中国", "lat": 22.5, "lon": 114.1}
    ]
    client, _ = _router_client(tmp_path, fake)
    first = client.get("/api/geocode", params={"q": "深圳"}).json()
    second = client.get("/api/geocode", params={"q": " 深圳 "}).json()
    assert first == second
    assert first[0]["display_name"] == "广东 · 中国"
    assert fake.calls["geocode"] == 1


def test_geocode_validation_and_safe_failure(tmp_path) -> None:
    fake = FakeWeather()
    fake.fail_geocode = True
    client, _ = _router_client(tmp_path, fake)
    assert client.get("/api/geocode", params={"q": " "}).status_code == 422
    assert client.get("/api/geocode", params={"q": "x" * 61}).status_code == 422

    response = client.get("/api/geocode", params={"q": "深圳"})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail == "天气服务暂时不可用"
    assert "http" not in detail and "Traceback" not in detail


def test_first_location_is_default_and_can_switch(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    shenzhen = client.post(
        "/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1}
    ).json()
    sanya = client.post(
        "/api/locations", json={"name": "三亚", "lat": 18.25, "lon": 109.5}
    ).json()
    assert shenzhen["is_default"] is True
    assert sanya["is_default"] is False
    assert shenzhen["climate_ready"] is True

    switched = client.post(f"/api/locations/{sanya['id']}/default").json()
    assert switched["is_default"] is True
    locations = client.get("/api/locations").json()
    assert [row["name"] for row in locations] == ["三亚", "深圳"]
    assert [row["is_default"] for row in locations] == [True, False]


def test_weather_follows_switched_default_location(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    client.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})
    sanya = client.post(
        "/api/locations", json={"name": "三亚", "lat": 18.25, "lon": 109.5}
    ).json()

    assert client.get("/api/weather").json()["location"]["name"] == "深圳"
    assert fake.forecast_coords == [(22.5, 114.1)]

    client.post(f"/api/locations/{sanya['id']}/default")
    assert client.get("/api/weather").json()["location"]["name"] == "三亚"
    assert fake.forecast_coords[-1] == (18.25, 109.5)


def test_location_duplicate_and_bounds(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    payload = {"name": "深圳", "lat": 22.5, "lon": 114.1}
    assert client.post("/api/locations", json=payload).status_code == 201
    duplicate = client.post("/api/locations", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "这个地点已经加过了"
    assert client.post(
        "/api/locations", json={"name": "坏", "lat": 91, "lon": 0}
    ).status_code == 422
    assert client.post(
        "/api/locations", json={"name": " ", "lat": 0, "lon": 0}
    ).status_code == 422


def test_location_survives_climate_failure_and_can_retry(tmp_path) -> None:
    fake = FakeWeather()
    fake.fail_climate = True
    client, db = _router_client(tmp_path, fake)
    added = client.post(
        "/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1}
    )
    assert added.status_code == 201
    assert added.json()["climate_ready"] is False

    retry = client.post(f"/api/locations/{added.json()['id']}/climate")
    assert retry.status_code == 502

    fake.fail_climate = False
    retry = client.post(f"/api/locations/{added.json()['id']}/climate")
    assert retry.status_code == 200
    assert retry.json() == {
        "location_id": added.json()["id"],
        "days": 10,
        "climate_ready": True,
    }
    assert client.get("/api/locations").json()[0]["climate_ready"] is True
    conn = connect(db)
    try:
        rows = conn.execute("SELECT COUNT(*) FROM climate_profile").fetchone()[0]
    finally:
        conn.close()
    assert rows == 10


def test_climate_retry_unknown_location_is_404(tmp_path) -> None:
    client, _ = _router_client(tmp_path, FakeWeather())
    assert client.post("/api/locations/999/climate").status_code == 404
    assert client.post("/api/locations/999/default").status_code == 404


# ---------------------------------------------------------------------------
# 天气
# ---------------------------------------------------------------------------


def test_weather_without_location_does_not_call_upstream(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    body = client.get("/api/weather").json()
    assert body["location"] is None
    assert body["source"] == "none"
    assert body["feels_like"] is None
    assert body["offline"] is False
    assert fake.calls["forecast"] == 0


def test_weather_forecast_and_cache(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    client.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})

    first = client.get("/api/weather").json()
    assert first["source"] == "forecast"
    assert first["feels_like"] == 27.4
    assert first["is_apparent"] is True
    assert first["offline"] is False
    assert first["climate_ready"] is True
    assert first["location"]["name"] == "深圳"

    client.get("/api/weather")
    assert fake.calls["forecast"] == 1
    client.get("/api/weather", params={"refresh": "1"})
    assert fake.calls["forecast"] == 2


def test_weather_falls_back_to_climate(tmp_path) -> None:
    fake = FakeWeather()
    client, _ = _router_client(tmp_path, fake)
    client.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})
    fake.fail_forecast = True

    body = client.get("/api/weather").json()
    assert body["source"] == "climate"
    assert body["feels_like"] == 24.5
    assert body["is_apparent"] is True
    assert body["offline"] is True
    assert body["is_rainy"] is False
    assert body["condition"] == "近十年同期"


def test_weather_none_when_forecast_and_climate_fail(tmp_path) -> None:
    fake = FakeWeather()
    fake.fail_climate = True
    client, _ = _router_client(tmp_path, fake)
    client.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})
    fake.fail_forecast = True

    body = client.get("/api/weather").json()
    assert body["source"] == "none"
    assert body["feels_like"] is None
    assert body["offline"] is True
    assert body["climate_ready"] is False


def test_weather_rain_flag_comes_from_forecast(tmp_path) -> None:
    fake = FakeWeather()
    fake.forecast_result["is_rainy"] = True
    fake.forecast_result["weather_code"] = 61
    fake.forecast_result["condition"] = "小雨"
    client, _ = _router_client(tmp_path, fake)
    client.post("/api/locations", json={"name": "深圳", "lat": 22.5, "lon": 114.1})
    assert client.get("/api/weather").json()["is_rainy"] is True


# ---------------------------------------------------------------------------
# 统计与导出
# ---------------------------------------------------------------------------


def test_stats_counts_items_photos_and_rules(tmp_path) -> None:
    items = [
        layer_item("base", id=1),
        layer_item("base", id=2),
        layer_item("base", id=3, status="draft"),
        layer_item("base", id=4, status="archived"),
    ]
    client, _ = _app_client(tmp_path, FakeWeather(), items)
    pic = tmp_path / "pic"
    photos = tmp_path / "photos"
    (pic / "a.jpg").write_bytes(b"aaa")
    (pic / "b.JPG").write_bytes(b"bb")
    (pic / "note.txt").write_text("x")
    (pic / ".hidden.jpg").write_bytes(b"hidden")
    (photos / "c.png").write_bytes(b"cccc")
    os.symlink(tmp_path / "outside.jpg", photos / "link.jpg")

    body = client.get("/api/stats").json()
    assert body["items"] == {
        "confirmed": 2, "draft": 1, "archived": 1, "total": 4
    }
    assert body["locations"] == 0
    assert body["photos"] == {"count": 3, "bytes": 9}
    assert body["db_bytes"] > 0
    assert body["profile_complete"] is False
    assert body["rules"] == 26
    assert body["version"] == "0.1.0"


def test_export_zip_has_snapshot_manifest_and_no_photo_bytes(tmp_path) -> None:
    (tmp_path / "pic").mkdir()
    (tmp_path / "photos").mkdir()
    (tmp_path / "pic" / "1.jpg").write_bytes(b"pic-one")
    (tmp_path / "pic" / "1-extra.jpg").write_bytes(b"pic-extra")
    (tmp_path / "photos" / "new.jpg").write_bytes(b"new-one")
    (tmp_path / "outside.jpg").write_bytes(b"secret")
    os.symlink(tmp_path / "outside.jpg", tmp_path / "photos" / "link.jpg")

    items = [
        layer_item("base", id=1, name="A", photo_path="pic/1.jpg",
                   cutout_path="photos/new.jpg",
                   extra_photos=("pic/1-extra.jpg", "../evil.jpg")),
        layer_item("base", id=2, name="B", photo_path="../secret.jpg"),
        layer_item("base", id=3, name="C", photo_path="/etc/passwd"),
        layer_item("base", id=4, name="D", photo_path="photos/link.jpg"),
        layer_item("base", id=5, name="E", photo_path="photos/missing.jpg"),
    ]
    client, db = _app_client(tmp_path, FakeWeather(), items)

    response = client.get("/api/export")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "wardrobe-export-" in response.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"wardrobe.db", "photos.json", "README.txt"}
        manifest = json.loads(archive.read("photos.json"))
        exported = archive.read("wardrobe.db")

    assert "pic-one" not in response.content.decode("latin-1")
    assert "new-one" not in response.content.decode("latin-1")

    by_path = {entry["path"]: entry for entry in manifest["photos"]}
    good = by_path["pic/1.jpg"]
    assert good["safe"] is True and good["exists"] is True
    assert good["bytes"] == 7
    assert good["sha256"] == hashlib.sha256(b"pic-one").hexdigest()
    assert by_path["photos/new.jpg"]["sha256"] == hashlib.sha256(b"new-one").hexdigest()
    extra = by_path["pic/1-extra.jpg"]
    assert extra["kind"] == "extra"
    assert extra["safe"] is True and extra["exists"] is True
    assert extra["sha256"] == hashlib.sha256(b"pic-extra").hexdigest()

    assert by_path["../evil.jpg"]["kind"] == "extra"
    assert by_path["../evil.jpg"]["safe"] is False

    assert by_path["../secret.jpg"]["safe"] is False
    assert by_path["../secret.jpg"]["exists"] is False
    assert by_path["/etc/passwd"]["safe"] is False
    assert by_path["photos/link.jpg"]["safe"] is False
    assert by_path["photos/missing.jpg"]["safe"] is True
    assert by_path["photos/missing.jpg"]["exists"] is False

    snapshot = tmp_path / "snapshot.db"
    snapshot.write_bytes(exported)
    conn = sqlite3.connect(snapshot)
    try:
        assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 5
    finally:
        conn.close()
