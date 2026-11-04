"""API 单测：响应结构、状态过滤、锚定、参数校验、反馈写入与录入。"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest
from factories import layer_item
from fastapi.testclient import TestClient
from PIL import Image
from src.api.app import create_app
from src.db.connection import connect, init_db
from src.db.repo import insert_item, load_feedback, load_items, outfit_hash
from src.rules.solver import solve
from src.rules.theory import AXIS_LABELS, AXIS_ORDER
from src.rules.types import Context


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "api.db"
    conn = connect(path)
    init_db(conn)
    insert_item(conn, layer_item(
        "base",
        id=1,
        name="白T恤",
        length_cm=68,
        shoulder_cm=43,
        chest_width_cm=50,
    ))
    insert_item(conn, layer_item(
        "base",
        id=2,
        name="灰T恤",
        length_cm=69,
        shoulder_cm=44,
        chest_width_cm=51,
    ))
    insert_item(conn, layer_item("bottom", id=3, name="牛仔裤"))
    insert_item(conn, layer_item("shoes", id=4, name="小白鞋", shoe_size=42))
    insert_item(conn, layer_item("base", id=5, name="草稿T恤", status="draft"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    return TestClient(create_app(db_path, photo_dir=tmp_path / "photos"))


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_items_default_to_confirmed_only(client: TestClient) -> None:
    confirmed = client.get("/api/items").json()
    assert [item["id"] for item in confirmed] == [1, 2, 3, 4]

    drafts = client.get("/api/items", params={"status": "draft"}).json()
    assert [item["id"] for item in drafts] == [5]

    everything = client.get("/api/items", params={"status": "all"}).json()
    assert {item["status"] for item in everything} == {"confirmed", "draft"}


def test_gaps_insufficient_below_five_items(client: TestClient) -> None:
    body = client.get("/api/gaps").json()
    assert body["basis"] == {
        "item_count": 4,
        "sufficient": False,
        "strict": True,
        "bands": [],
    }
    assert body["bottlenecks"] == []
    assert body["isolated"] == []
    assert body["occasions"] == []
    assert body["fills"] == []


def test_outfits_response_shape(client: TestClient) -> None:
    response = client.get("/api/outfits", params={"feels_like": 22})
    assert response.status_code == 200
    body = response.json()

    assert body["context"] == {
        "occasion": "日常",
        "feels_like": 22.0,
        "is_rainy": False,
        "height_cm": None,
    }
    assert body["candidate_count"] == 2
    assert body["best_level"] == 0
    assert body["all_rejected"] is False
    assert body["has_more"] is False
    assert set(body["level_counts"]) == {"0", "1", "2", "3"}
    assert len(body["outfits"]) == 2

    outfit = body["outfits"][0]
    assert set(outfit) == {
        "hash",
        "score",
        "level",
        "relaxed_rules",
        "reason",
        "explanation",
        "thumbs_up",
        "thumbs_down",
        "items",
    }
    assert [piece["slot"] for piece in outfit["items"]] == [
        "base_top",
        "bottom",
        "shoes",
    ]
    assert [piece["slot_label"] for piece in outfit["items"]] == ["内搭", "下装", "鞋"]
    assert len(outfit["hash"]) == 16


def test_outfits_include_structured_explanation(client: TestClient) -> None:
    body = client.get("/api/outfits", params={"feels_like": 22}).json()
    assert len(body["outfits"]) == 2
    for outfit in body["outfits"]:
        assert isinstance(outfit["reason"], str) and outfit["reason"]
        explanation = outfit["explanation"]
        assert set(explanation) == {
            "headline",
            "principles",
            "caveats",
            "style",
            "data_gaps",
            "version",
        }
        assert explanation["version"] == "explain-v1"
        assert explanation["headline"]
        assert 1 <= len(explanation["principles"]) <= 5
        assert len(explanation["caveats"]) <= 3
        assert len(explanation["data_gaps"]) <= 2
        line = explanation["principles"][0]
        assert set(line) == {
            "principle_id",
            "rule_id",
            "title",
            "evidence",
            "why",
            "how_to_judge",
            "grade",
            "grade_label",
            "source",
            "source_url",
            "kind",
        }
        assert line["principle_id"].startswith("P-")
        assert line["rule_id"].startswith("R-")
        assert line["evidence"]
        assert explanation["style"]["inferred"] is True
        assert explanation["style"]["basis"]


def test_theory_endpoint_is_complete(client: TestClient) -> None:
    response = client.get("/api/theory")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"groups", "unsupported"}
    assert [group["axis"] for group in body["groups"]] == [
        AXIS_LABELS[axis] for axis in AXIS_ORDER
    ]
    principles = [p for group in body["groups"] for p in group["principles"]]
    assert len(principles) == 18
    assert len({p["id"] for p in principles}) == 18
    for principle in principles:
        assert principle["grade"] in {"A", "B", "C", "D"}
        assert principle["status"] in {
            "active",
            "conditional",
            "baseline",
            "boundary",
            "dormant",
        }
        assert principle["status_label"]
        assert principle["rule_ids"]
    assert len(body["unsupported"]) >= 8


def test_solve_does_not_call_explain(db_path, monkeypatch) -> None:
    conn = connect(db_path)
    try:
        items = load_items(conn)
    finally:
        conn.close()

    def _boom(*args, **kwargs):
        raise AssertionError("solve() 不应调用解释层")

    monkeypatch.setattr("src.rules.explain.explain", _boom)
    result = solve(items, Context(occasion="日常", feels_like=22), limit=2)
    assert result.outfits


def test_anchor_only_returns_outfits_containing_it(client: TestClient) -> None:
    body = client.get(
        "/api/outfits", params={"anchor_id": 2, "feels_like": 22}
    ).json()
    assert len(body["outfits"]) == 1
    assert 2 in [piece["id"] for piece in body["outfits"][0]["items"]]


def test_anchor_missing_or_draft_is_404(client: TestClient) -> None:
    assert client.get("/api/outfits", params={"anchor_id": 999}).status_code == 404
    # 草稿不参与求解，锚定它同样视为不可用
    assert client.get("/api/outfits", params={"anchor_id": 5}).status_code == 404


def test_limit_and_invalid_inputs(client: TestClient) -> None:
    assert len(client.get("/api/outfits", params={"limit": 1, "feels_like": 22}).json()["outfits"]) == 1
    assert client.get("/api/outfits", params={"occasion": "健身"}).status_code == 422
    assert client.get("/api/outfits", params={"limit": 0}).status_code == 422
    assert client.get("/api/outfits", params={"offset": -1}).status_code == 422
    assert client.get("/api/outfits", params={"feels_like": 99}).status_code == 422


def test_outfits_offset_pages_without_overlap(client: TestClient) -> None:
    first = client.get(
        "/api/outfits", params={"feels_like": 22, "limit": 1}
    ).json()
    second = client.get(
        "/api/outfits", params={"feels_like": 22, "limit": 1, "offset": 1}
    ).json()

    assert len(first["outfits"]) == 1
    assert len(second["outfits"]) == 1
    assert first["outfits"][0]["hash"] != second["outfits"][0]["hash"]
    assert first["has_more"] is True
    assert second["has_more"] is False

    # 翻过末尾：返回空页，但不是「这个条件下无解」
    beyond = client.get(
        "/api/outfits", params={"feels_like": 22, "limit": 1, "offset": 5}
    ).json()
    assert beyond["outfits"] == []
    assert beyond["has_more"] is False
    assert beyond["all_rejected"] is False
    assert beyond["best_level"] == 0


def test_empty_wardrobe_returns_empty_result(tmp_path) -> None:
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()
    body = TestClient(create_app(db_path)).get("/api/outfits").json()
    assert body["candidate_count"] == 0
    assert body["outfits"] == []
    assert body["all_rejected"] is True
    assert body["best_level"] is None


def _first_outfit(client: TestClient) -> dict:
    return client.get("/api/outfits", params={"feels_like": 22}).json()["outfits"][0]


def _feedback_body(outfit: dict, signal: str, **extra) -> dict:
    return {
        "outfit_hash": outfit["hash"],
        "signal": signal,
        "garment_ids": [piece["id"] for piece in outfit["items"]],
        "hit_rules": outfit["thumbs_up"] + outfit["thumbs_down"],
        **extra,
    }


def test_feedback_adopt_records_and_marks_last_worn(client: TestClient) -> None:
    outfit = _first_outfit(client)
    response = client.post("/api/feedback", json=_feedback_body(outfit, "adopt"))
    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "outfit_hash": outfit["hash"],
        "signal": "adopt",
        "garment_id": None,
    }

    items = {item["id"]: item for item in client.get("/api/items").json()}
    worn = {piece["id"] for piece in outfit["items"]}
    today = date.today().isoformat()
    assert all(items[item_id]["last_worn_at"] == today for item_id in worn)
    assert all(
        item["last_worn_at"] is None
        for item_id, item in items.items()
        if item_id not in worn
    )


def test_feedback_favorite_does_not_touch_last_worn(client: TestClient) -> None:
    outfit = _first_outfit(client)
    assert client.post(
        "/api/feedback", json=_feedback_body(outfit, "favorite")
    ).status_code == 201
    assert all(
        item["last_worn_at"] is None for item in client.get("/api/items").json()
    )


def test_feedback_ignore_is_recorded_without_side_effects(
    client: TestClient, db_path
) -> None:
    outfit = _first_outfit(client)
    response = client.post("/api/feedback", json=_feedback_body(outfit, "ignore"))
    assert response.status_code == 201
    assert response.json()["signal"] == "ignore"

    conn = connect(db_path)
    try:
        rows = load_feedback(conn, outfit["hash"])
    finally:
        conn.close()
    assert [row["signal"] for row in rows] == ["ignore"]
    assert all(
        item["last_worn_at"] is None for item in client.get("/api/items").json()
    )


def test_feedback_veto_requires_member_garment(client: TestClient) -> None:
    outfit = _first_outfit(client)
    member = outfit["items"][0]["id"]

    assert client.post(
        "/api/feedback",
        json=_feedback_body(outfit, "veto_item", garment_id=member),
    ).status_code == 201
    assert client.post(
        "/api/feedback", json=_feedback_body(outfit, "veto_item")
    ).status_code == 400
    assert client.post(
        "/api/feedback",
        json=_feedback_body(outfit, "veto_item", garment_id=999),
    ).status_code == 400
    assert client.post(
        "/api/feedback", json=_feedback_body(outfit, "adopt", garment_id=member)
    ).status_code == 400


def test_feedback_rejects_hash_mismatch_and_unknown_items(client: TestClient) -> None:
    outfit = _first_outfit(client)
    tampered = {**_feedback_body(outfit, "swap"), "outfit_hash": "0" * 16}
    assert client.post("/api/feedback", json=tampered).status_code == 400

    ids = [piece["id"] for piece in outfit["items"]]
    ghost_ids = [*ids[:-1], 999]
    ghost = {
        "outfit_hash": outfit_hash(ghost_ids),
        "signal": "swap",
        "garment_ids": ghost_ids,
    }
    assert client.post("/api/feedback", json=ghost).status_code == 400


def test_feedback_rejects_malformed_input(client: TestClient) -> None:
    outfit = _first_outfit(client)
    base = _feedback_body(outfit, "adopt")

    assert client.post(
        "/api/feedback", json={**base, "signal": "love"}
    ).status_code == 422
    assert client.post(
        "/api/feedback", json={**base, "outfit_hash": "not-a-hash"}
    ).status_code == 422
    assert client.post(
        "/api/feedback", json={**base, "garment_ids": []}
    ).status_code == 422
    assert client.post(
        "/api/feedback", json={**base, "garment_ids": [1, 1]}
    ).status_code == 422
    assert client.post(
        "/api/feedback", json={**base, "hit_rules": ["COL-01"]}
    ).status_code == 422


def test_feedback_persists_hit_rules(client: TestClient, db_path) -> None:
    outfit = _first_outfit(client)
    body = _feedback_body(outfit, "favorite")
    client.post("/api/feedback", json=body)

    conn = connect(db_path)
    try:
        rows = load_feedback(conn, outfit["hash"])
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0]["signal"] == "favorite"
    assert rows[0]["hit_rules"] == body["hit_rules"]


# ---------------------------------------------------------------------------
# 每日建议
# ---------------------------------------------------------------------------


def _suggestion_rows(db_path) -> list[dict]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT day, outfit_hash, garment_ids, hit_rules FROM daily_suggestion "
            "ORDER BY day"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "day": row["day"],
            "outfit_hash": row["outfit_hash"],
            "garment_ids": json.loads(row["garment_ids"]),
            "hit_rules": json.loads(row["hit_rules"]),
        }
        for row in rows
    ]


def test_today_returns_one_outfit_and_records_it(client: TestClient, db_path) -> None:
    body = client.get("/api/today", params={"feels_like": 22}).json()

    assert len(body["outfits"]) == 1
    assert body["context"] == {
        "occasion": "日常",
        "feels_like": 22.0,
        "is_rainy": False,
        "height_cm": None,
    }
    assert body["outfits"][0] == _first_outfit(client)

    shown = body["outfits"][0]
    rows = _suggestion_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["day"] == date.today().isoformat()
    assert rows[0]["outfit_hash"] == shown["hash"]
    assert rows[0]["garment_ids"] == sorted(piece["id"] for piece in shown["items"])
    assert rows[0]["hit_rules"] == shown["thumbs_up"] + shown["thumbs_down"]


def test_today_swap_overwrites_same_day_row(client: TestClient, db_path) -> None:
    first = client.get("/api/today", params={"feels_like": 22}).json()["outfits"][0]
    second = client.get(
        "/api/today", params={"feels_like": 22, "offset": 1}
    ).json()["outfits"][0]

    assert first["hash"] != second["hash"]
    rows = _suggestion_rows(db_path)
    assert len(rows) == 1
    assert rows[0]["outfit_hash"] == second["hash"]


def test_today_rotation_avoids_recently_worn_items(client: TestClient, db_path) -> None:
    conn = connect(db_path)
    try:
        conn.execute(
            "UPDATE item SET last_worn_at = ? WHERE id = 1",
            (date.today().isoformat(),),
        )
        conn.commit()
    finally:
        conn.close()

    shown = client.get("/api/today", params={"feels_like": 22}).json()["outfits"][0]
    assert 1 not in [piece["id"] for piece in shown["items"]]


def test_today_backfills_ignore_for_yesterday_when_unfeedback(
    client: TestClient, db_path, monkeypatch
) -> None:
    import src.api.app as app_module

    shown = client.get("/api/today", params={"feels_like": 22}).json()["outfits"][0]
    tomorrow = date.today() + timedelta(days=1)
    monkeypatch.setattr(app_module, "_local_today", lambda: tomorrow)

    client.get("/api/today", params={"feels_like": 22})

    conn = connect(db_path)
    try:
        rows = load_feedback(conn, shown["hash"])
    finally:
        conn.close()
    assert [(row["signal"], row["hit_rules"]) for row in rows] == [
        ("ignore", shown["thumbs_up"] + shown["thumbs_down"])
    ]
    assert [row["day"] for row in _suggestion_rows(db_path)] == [
        tomorrow.isoformat()
    ]


def test_today_does_not_backfill_when_yesterday_got_feedback(
    client: TestClient, db_path, monkeypatch
) -> None:
    import src.api.app as app_module

    shown = client.get("/api/today", params={"feels_like": 22}).json()["outfits"][0]
    client.post("/api/feedback", json=_feedback_body(shown, "swap"))
    tomorrow = date.today() + timedelta(days=1)
    monkeypatch.setattr(app_module, "_local_today", lambda: tomorrow)

    client.get("/api/today", params={"feels_like": 22})

    conn = connect(db_path)
    try:
        rows = load_feedback(conn, shown["hash"])
    finally:
        conn.close()
    assert [row["signal"] for row in rows] == ["swap"]
    assert [row["day"] for row in _suggestion_rows(db_path)] == [
        tomorrow.isoformat()
    ]


def test_today_empty_wardrobe_writes_no_suggestion(tmp_path) -> None:
    db_path = tmp_path / "empty.db"
    sqlite3.connect(db_path).close()
    body = TestClient(create_app(db_path)).get("/api/today").json()

    assert body["outfits"] == []
    assert body["all_rejected"] is True
    assert _suggestion_rows(db_path) == []


# ---------------------------------------------------------------------------
# 录入：POST /api/items
# ---------------------------------------------------------------------------


def _item_payload(**overrides) -> dict:
    """一件外套：默认属性齐全、四项尺寸齐全，可直接 confirmed。"""
    payload = {
        "name": "试录外套",
        "category": "外套",
        "layers": ["outer"],
        "formality": 3,
        "color_hex": "#2f4156",
        "fit": "regular",
        "pattern": "solid",
        "weight": "medium",
        "length_cm": 66.5,
        "shoulder_cm": 44,
        "chest_width_cm": 52,
        "sleeve_cm": 60,
    }
    payload.update(overrides)
    return payload


def _data_url(size=(900, 1200), color=(210, 60, 40)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def test_create_confirmed_item_with_photos(client: TestClient, tmp_path) -> None:
    response = client.post(
        "/api/items",
        json=_item_payload(
            photos_data=[
                _data_url(color=(210, 60, 40)),
                _data_url(size=(400, 300), color=(60, 210, 40)),
                _data_url(size=(300, 300), color=(40, 60, 210)),
            ]
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 6
    assert body["status"] == "confirmed"
    assert body["color_hex"] == "#2F4156"
    assert body["layers"] == ["outer"]
    assert body["last_worn_at"] is None
    assert body["photo_path"].startswith("photos/")

    detail = client.get(f"/api/items/{body['id']}").json()
    assert len(detail["photos"]) == 3
    assert detail["photos"][0] == body["photo_path"]
    assert len(set(detail["photos"])) == 3
    for path in detail["photos"]:
        assert (tmp_path / "photos" / Path(path).name).is_file()
        assert client.get("/" + path).status_code == 200


def test_saved_photo_is_downscaled_and_exif_free(client: TestClient, tmp_path) -> None:
    response = client.post(
        "/api/items",
        json=_item_payload(photos_data=[_data_url(size=(2400, 1200))]),
    )
    assert response.status_code == 201

    saved = tmp_path / "photos" / Path(response.json()["photo_path"]).name
    with Image.open(saved) as img:
        assert max(img.size) == 1600
        assert img.mode == "RGB"
        assert not img.getexif()


def test_confirmed_item_can_have_no_photo(client: TestClient) -> None:
    response = client.post("/api/items", json=_item_payload())

    assert response.status_code == 201
    assert response.json()["photo_path"] is None
    assert response.json()["status"] == "confirmed"


def test_confirmed_outer_missing_size_is_rejected(client: TestClient) -> None:
    response = client.post("/api/items", json=_item_payload(sleeve_cm=None))

    assert response.status_code == 422
    assert "袖长" in response.text


def test_confirmed_bottom_requires_four_sizes(client: TestClient) -> None:
    bottom = _item_payload(
        name="试录牛仔裤",
        category="牛仔裤",
        layers=["bottom"],
        length_cm=95,
        waist_cm=78,
        hip_cm=100,
        shoulder_cm=None,
        chest_width_cm=None,
        sleeve_cm=None,
    )
    response = client.post("/api/items", json=bottom)
    assert response.status_code == 422
    assert "裤口" in response.text

    ok = client.post("/api/items", json={**bottom, "leg_opening_cm": 17})
    assert ok.status_code == 201


def _top_payload(category: str = "T恤", **overrides) -> dict:
    """一件上衣：衣长、肩宽、胸宽齐全，袖长留空。"""
    payload = _item_payload(
        name=f"试录{category}",
        category=category,
        layers=["inner"],
        length_cm=68,
        shoulder_cm=43,
        chest_width_cm=50,
        sleeve_cm=None,
    )
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("category", ["T恤", "衬衫", "卫衣", "毛衣", "针织"])
def test_confirmed_top_requires_length(client: TestClient, category: str) -> None:
    missing = client.post("/api/items", json=_top_payload(category, length_cm=None))
    assert missing.status_code == 422
    assert "衣长" in missing.text

    ok = client.post("/api/items", json=_top_payload(category))
    assert ok.status_code == 201
    assert ok.json()["status"] == "confirmed"


def test_top_without_sleeve_can_still_be_confirmed(client: TestClient) -> None:
    response = client.post("/api/items", json=_top_payload("衬衫"))
    assert response.status_code == 201
    detail = client.get(f"/api/items/{response.json()['id']}").json()
    assert detail["sleeve_cm"] is None
    assert detail["length_cm"] == 68


def test_draft_top_skips_length_requirement(client: TestClient) -> None:
    response = client.post(
        "/api/items", json=_top_payload("针织", length_cm=None, status="draft")
    )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"


def _shoe_payload(**overrides) -> dict:
    payload = _item_payload(
        name="试录跑鞋",
        category="鞋",
        layers=["shoes"],
        length_cm=None,
        shoulder_cm=None,
        chest_width_cm=None,
        sleeve_cm=None,
        shoe_size=42,
    )
    payload.update(overrides)
    return payload


def test_confirmed_shoe_requires_eu_size(client: TestClient) -> None:
    missing = client.post("/api/items", json=_shoe_payload(shoe_size=None))
    assert missing.status_code == 422
    assert "鞋码" in missing.text

    ok = client.post("/api/items", json=_shoe_payload())
    assert ok.status_code == 201
    item_id = ok.json()["id"]
    assert client.get(f"/api/items/{item_id}").json()["shoe_size"] == 42


def test_shoe_size_accepts_half_size_and_rejects_out_of_range(
    client: TestClient,
) -> None:
    assert client.post("/api/items", json=_shoe_payload(shoe_size=42.5)).status_code == 201
    assert client.post("/api/items", json=_shoe_payload(shoe_size=61)).status_code == 422


def test_draft_shoe_skips_size_requirement(client: TestClient) -> None:
    response = client.post(
        "/api/items", json=_shoe_payload(shoe_size=None, status="draft")
    )
    assert response.status_code == 201
    assert response.json()["status"] == "draft"


def test_patch_can_fill_shoe_size(client: TestClient) -> None:
    created = client.post(
        "/api/items", json=_shoe_payload(shoe_size=None, status="draft")
    ).json()

    confirmed = client.patch(
        f"/api/items/{created['id']}", json={"shoe_size": 42.5, "status": "confirmed"}
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["shoe_size"] == 42.5
    assert confirmed.json()["status"] == "confirmed"


def test_draft_needs_no_sizes_and_accepts_partial(client: TestClient) -> None:
    response = client.post(
        "/api/items",
        json=_item_payload(status="draft", sleeve_cm=None, chest_width_cm=None),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "draft"
    assert body["id"] == 6


def test_layers_rules_per_category(client: TestClient) -> None:
    missing = client.post("/api/items", json=_item_payload(layers=[]))
    assert missing.status_code == 422

    onesie = client.post(
        "/api/items",
        json=_item_payload(name="连衣裙", category="连体装", status="draft", layers=[]),
    )
    assert onesie.status_code == 201

    onesie_with_layer = client.post(
        "/api/items",
        json=_item_payload(name="连衣裙", category="连体装", status="draft", layers=["inner"]),
    )
    assert onesie_with_layer.status_code == 422


def test_invalid_enums_and_color_are_rejected(client: TestClient) -> None:
    for overrides in (
        {"color_hex": "2f4156"},
        {"category": "帽子"},
        {"layers": ["top"]},
        {"layers": ["outer", "outer"]},
        {"fit": "loose"},
        {"weight": "warm"},
        {"formality": 6},
        {"length_cm": 0},
    ):
        response = client.post("/api/items", json=_item_payload(**overrides))
        assert response.status_code == 422, overrides


def test_unknown_material_and_collar_become_null(client: TestClient) -> None:
    response = client.post(
        "/api/items", json=_item_payload(material="不确定", collar="不适用")
    )

    assert response.status_code == 201
    assert response.json()["material"] is None
    assert response.json()["collar"] is None


def test_bad_photo_is_rejected_without_leaking_paths(client: TestClient) -> None:
    headers = {"content-type": "application/json"}
    for photo in (
        "data:image/jpeg;base64,bm90IGFuIGltYWdl",
        "data:text/plain;base64,aGVsbG8=",
        "not-a-data-url",
    ):
        response = client.post(
            "/api/items", json=_item_payload(photos_data=[photo]), headers=headers
        )
        assert response.status_code == 400, photo
        assert "Traceback" not in response.text
        assert str(client.app) not in response.text


def test_ids_increment_and_new_items_are_listed(client: TestClient) -> None:
    first = client.post("/api/items", json=_item_payload()).json()
    second = client.post(
        "/api/items", json=_item_payload(name="草稿卫衣", category="卫衣", status="draft")
    ).json()

    assert (first["id"], second["id"]) == (6, 7)

    everything = client.get("/api/items", params={"status": "all"}).json()
    assert {item["id"]: item["status"] for item in everything} == {
        1: "confirmed",
        2: "confirmed",
        3: "confirmed",
        4: "confirmed",
        5: "draft",
        6: "confirmed",
        7: "draft",
    }
    confirmed = client.get("/api/items").json()
    assert [item["id"] for item in confirmed] == [1, 2, 3, 4, 6]


# ---------------------------------------------------------------------------
# 详情与编辑：GET / PATCH /api/items/{id}
# ---------------------------------------------------------------------------


def test_item_detail_includes_sizes_and_seasons(client: TestClient) -> None:
    response = client.get("/api/items/1")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "白T恤"
    assert isinstance(body["seasons"], list)
    assert body["length_cm"] == 68
    assert body["leg_opening_cm"] is None
    assert body["photos"] == []
    assert body["shoe_size"] is None

    shoe = client.get("/api/items/4").json()
    assert shoe["shoe_size"] == 42

    missing = client.get("/api/items/999")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "单品不存在"


def test_item_list_stays_lightweight(client: TestClient) -> None:
    listed = client.get("/api/items").json()
    assert listed
    for item in listed:
        assert "photos" not in item
        assert "shoe_size" not in item


def test_patch_updates_attributes_and_recomputes_seasons(
    client: TestClient, db_path
) -> None:
    conn = connect(db_path)
    try:
        conn.execute("UPDATE item SET last_worn_at = '2026-10-01' WHERE id = 1")
        conn.commit()
    finally:
        conn.close()

    response = client.patch(
        "/api/items/1",
        json={
            "name": "米白T恤",
            "color_hex": "#abcdef",
            "weight": "thick",
            "material": "棉",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "米白T恤"
    assert body["color_hex"] == "#ABCDEF"
    assert body["seasons"] == ["winter"]
    assert body["material"] == "棉"
    assert body["last_worn_at"] == "2026-10-01"

    persisted = client.get("/api/items/1").json()
    assert persisted["name"] == "米白T恤"
    assert persisted["color_hex"] == "#ABCDEF"


def test_patch_can_clear_optional_fields_but_not_required_ones(
    client: TestClient,
) -> None:
    assert client.patch(
        "/api/items/1", json={"material": "棉", "collar": "翻领"}
    ).status_code == 200
    cleared = client.patch("/api/items/1", json={"material": None, "collar": None})
    assert cleared.status_code == 200
    assert cleared.json()["material"] is None
    assert cleared.json()["collar"] is None

    assert client.patch("/api/items/1", json={"formality": None}).status_code == 422


def test_patch_completes_draft_sizes_and_confirms(client: TestClient) -> None:
    created = client.post(
        "/api/items",
        json=_item_payload(status="draft", sleeve_cm=None, chest_width_cm=None),
    ).json()
    assert created["status"] == "draft"

    response = client.patch(
        f"/api/items/{created['id']}",
        json={"sleeve_cm": 61, "chest_width_cm": 51.5, "status": "confirmed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["sleeve_cm"] == 61
    assert created["id"] in [item["id"] for item in client.get("/api/items").json()]


def test_confirmed_patch_missing_size_is_422(client: TestClient) -> None:
    created = client.post("/api/items", json=_item_payload()).json()

    response = client.patch(f"/api/items/{created['id']}", json={"sleeve_cm": None})
    assert response.status_code == 422
    assert "袖长" in response.text

    assert client.patch(
        f"/api/items/{created['id']}", json={"sleeve_cm": None, "status": "draft"}
    ).status_code == 200


def test_patch_keeps_existing_photo(client: TestClient, tmp_path) -> None:
    created = client.post(
        "/api/items", json=_item_payload(photos_data=[_data_url()])
    ).json()
    saved = tmp_path / "photos" / Path(created["photo_path"]).name
    assert saved.is_file()

    response = client.patch(f"/api/items/{created['id']}", json={"name": "改名外套"})
    assert response.status_code == 200
    assert response.json()["photo_path"] == created["photo_path"]
    assert saved.is_file()


def test_patch_appends_photos_and_first_becomes_cover(
    client: TestClient, tmp_path
) -> None:
    created = client.post("/api/items", json=_item_payload()).json()
    assert created["photo_path"] is None

    added = client.patch(
        f"/api/items/{created['id']}", json={"photos_data": [_data_url()]}
    )
    assert added.status_code == 200
    photo_path = added.json()["photo_path"]
    assert photo_path.startswith("photos/")
    assert (tmp_path / "photos" / Path(photo_path).name).is_file()

    appended = client.patch(
        f"/api/items/{created['id']}",
        json={"photos_data": [_data_url(color=(10, 20, 30))]},
    )
    assert appended.status_code == 200
    detail = client.get(f"/api/items/{created['id']}").json()
    assert detail["photo_path"] == photo_path
    assert detail["photos"][0] == photo_path
    assert len(detail["photos"]) == 2


def test_patch_rejects_more_than_six_photos(client: TestClient) -> None:
    created = client.post("/api/items", json=_item_payload()).json()
    assert client.patch(
        f"/api/items/{created['id']}", json={"photos_data": [_data_url()] * 6}
    ).status_code == 200

    over = client.patch(
        f"/api/items/{created['id']}", json={"photos_data": [_data_url()]}
    )
    assert over.status_code == 422
    assert "最多 6 张照片" in over.json()["detail"]


def test_create_rejects_more_than_six_photos(client: TestClient) -> None:
    response = client.post(
        "/api/items", json=_item_payload(photos_data=[_data_url()] * 7)
    )
    assert response.status_code == 422
    assert "最多 6 张照片" in response.text


def test_patch_rejects_bad_photo_without_leaking_paths(client: TestClient) -> None:
    created = client.post("/api/items", json=_item_payload()).json()
    response = client.patch(
        f"/api/items/{created['id']}",
        json={"photos_data": ["data:image/jpeg;base64,bm90IGFuIGltYWdl"]},
    )
    assert response.status_code == 400
    assert "Traceback" not in response.text
    assert str(client.app) not in response.text


def test_archive_excludes_item_from_solving(client: TestClient) -> None:
    before = client.get("/api/outfits", params={"feels_like": 22}).json()
    assert before["item_count"] == 4

    archived = client.patch("/api/items/1", json={"status": "archived"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    after = client.get("/api/outfits", params={"feels_like": 22}).json()
    assert after["item_count"] == 3
    assert 1 not in {
        piece["id"] for outfit in after["outfits"] for piece in outfit["items"]
    }
    listed = client.get("/api/items", params={"status": "all"}).json()
    assert {item["id"]: item["status"] for item in listed}[1] == "archived"


def test_archived_item_is_read_only_until_restored(client: TestClient) -> None:
    assert client.patch("/api/items/1", json={"status": "archived"}).status_code == 200

    changed = client.patch("/api/items/1", json={"name": "新名字"})
    assert changed.status_code == 400
    assert "重新启用" in changed.json()["detail"]

    restored = client.patch("/api/items/1", json={"status": "confirmed"})
    assert restored.status_code == 200
    assert restored.json()["status"] == "confirmed"
    assert restored.json()["name"] == "白T恤"


def test_restore_with_missing_sizes_falls_back_to_draft(client: TestClient) -> None:
    created = client.post(
        "/api/items", json=_item_payload(status="draft", sleeve_cm=None)
    ).json()
    item_id = created["id"]
    assert client.patch(
        f"/api/items/{item_id}", json={"status": "archived"}
    ).status_code == 200

    rejected = client.patch(f"/api/items/{item_id}", json={"status": "confirmed"})
    assert rejected.status_code == 422
    assert "袖长" in rejected.text

    restored = client.patch(f"/api/items/{item_id}", json={"status": "draft"})
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"


def test_archive_rejects_attribute_changes(client: TestClient) -> None:
    response = client.patch(
        "/api/items/1", json={"status": "archived", "name": "顺手改名"}
    )
    assert response.status_code == 400
    assert "只能修改状态" in response.json()["detail"]


def test_patch_rejects_unknown_or_invalid_fields(client: TestClient) -> None:
    for payload in (
        {"nickname": "外套"},
        {"category": "帽子"},
        {"color_hex": "2f4156"},
        {"layers": ["top"]},
        {"name": ""},
        {"formality": 6},
        {"length_cm": 0},
    ):
        response = client.patch("/api/items/1", json=payload)
        assert response.status_code == 422, payload

