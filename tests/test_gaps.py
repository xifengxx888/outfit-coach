"""缺口诊断（`02` 第九节）的规则单测与真实衣柜回归基线。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from factories import layer_item, make_item
from src.db.connection import connect
from src.db.repo import load_items
from src.rules.gaps import (
    BANDS,
    DEP_THRESHOLD,
    SlotMetric,
    _isolated,
    _prototypes,
    _solve_bands,
    _unlock,
    diagnose,
)
from src.rules.solver import assess, dedup, solve
from src.rules.slots import enumerate_candidates
from src.rules.types import Context

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "db" / "wardrobe.db"
# 基线固定在 2026-10-26 的 18 件库存（id 1–18）。之后新增单品不改变这份
# 对照值，避免每扩一件库存就要重算一遍回归基线。
BASELINE_MAX_ID = 18
requires_real_db = pytest.mark.skipif(
    not REAL_DB.exists(), reason="真实衣柜数据库不在，跳过基线回归"
)


def _fixture_items():
    return [
        layer_item("base", id=1),
        layer_item("base", id=2, name="第二件T恤"),
        layer_item("bottom", id=3, fit="regular"),
        layer_item("shoes", id=4),
    ]


def _fake(ids: tuple[int, ...]):
    return type("FakeAssessment", (), {"garment_ids": ids})()


def _fake_wardrobe():
    return [
        make_item(id=1, category="T恤", layers=("inner",), formality=5),
        make_item(id=2, category="T恤", layers=("inner",), formality=5),
        make_item(id=3, category="裤子", layers=("bottom",), formality=5),
        make_item(id=4, category="鞋", layers=("shoes",), formality=5),
        make_item(id=5, category="配饰", layers=("accessory",), formality=5),
    ]


def _fake_valid(own_count: int, warm_count: int = 0):
    base = (2, 3, 4, 5)
    cold = [_fake((1, *base)) for _ in range(own_count)]
    cold += [_fake(base) for _ in range(10 - own_count)]
    warm = [_fake((1, *base)) for _ in range(warm_count)]
    warm += [_fake(base) for _ in range(10 - warm_count)]
    return {"cold": cold, "cool": [], "warm": warm, "hot": []}


def test_slot_metric_threshold_boundary() -> None:
    def metric(dep: float) -> SlotMetric:
        return SlotMetric(
            slot="bottom",
            item_count=3,
            minimum=4,
            thin=0.0,
            dependency=dep,
            driver_id=None,
            driver_band=None,
            used=0,
            remain=0,
            total=0,
            severity=0.0,
        )

    assert not metric(DEP_THRESHOLD).triggered
    assert metric(DEP_THRESHOLD + 0.001).triggered


def test_valid_outfits_match_solver() -> None:
    items = _fixture_items()
    _, valid = _solve_bands(items)
    for band in BANDS:
        result = solve(
            items,
            Context(occasion="日常", feels_like=band.feels_like),
            limit=1000,
        )
        strict = [outfit for outfit in result.outfits if outfit.level == 0]
        assert len(strict) == len(valid[band.key])


def test_exact_unlock_equals_full_resolve() -> None:
    items = _fixture_items()
    candidates, valid = _solve_bands(items)
    prototype = make_item(
        id=9,
        name="中性色直筒裤",
        category="裤子",
        layers=("bottom",),
        formality=3,
        weight="thin",
        fit="regular",
    )
    unlock = _unlock(prototype, items, candidates, valid)
    for band in BANDS:
        result = solve(
            [*items, prototype],
            Context(occasion="日常", feels_like=band.feels_like),
            limit=1000,
        )
        strict = [outfit for outfit in result.outfits if outfit.level == 0]
        assert unlock[band.key] == len(strict) - len(valid[band.key])


def test_isolated_hard_item() -> None:
    items = _fake_wardrobe()
    found = _isolated(items, {}, _fake_valid(own_count=0))
    assert found[0]["item_id"] == 1
    assert found[0]["kind"] == "hard"


def test_isolated_edge_item() -> None:
    items = _fake_wardrobe()
    found = _isolated(items, {}, _fake_valid(own_count=2))
    assert found[0]["item_id"] == 1
    assert found[0]["kind"] == "edge"


def test_isolated_formality_island() -> None:
    items = _fake_wardrobe()
    items[0] = make_item(
        id=1, name="亮橙卫衣", category="T恤", layers=("inner",), formality=1
    )
    found = _isolated(items, {}, _fake_valid(own_count=4))
    assert found[0]["item_id"] == 1
    assert found[0]["kind"] == "formality_island"


def test_seasonal_edge_is_not_flagged_when_one_band_supports_it() -> None:
    items = _fake_wardrobe()
    items = [
        make_item(id=item.id, category=item.category, layers=item.layers, formality=3)
        for item in items
    ]
    found = _isolated(items, {}, _fake_valid(own_count=2, warm_count=8))
    assert all(row["item_id"] != 1 for row in found)


@pytest.fixture(scope="module")
def real_case():
    conn = connect(REAL_DB)
    try:
        return [item for item in load_items(conn) if item.id <= BASELINE_MAX_ID]
    finally:
        conn.close()


@requires_real_db
def test_real_baseline(real_case) -> None:
    items = real_case
    report = diagnose(items)

    assert [band["valid_outfits"] for band in report["basis"]["bands"]] == [
        13,
        31,
        71,
        49,
    ]
    assert report["basis"]["sufficient"] is True

    first, second = report["bottlenecks"]
    assert first["slots"] == ["outer_layer", "mid_layer"]
    assert first["item_count"] == 2
    assert first["item_count_by_slot"] == {"outer_layer": 2, "mid_layer": 4}
    assert first["dependency"] == 0.54
    assert first["driver_item_id"] == 10
    assert first["driver_band"] == "cold"
    assert second["slots"] == ["bottom"]
    assert second["item_count"] == 3
    assert second["dependency"] == 0.42
    assert second["driver_item_id"] == 12
    assert second["driver_band"] == "cool"
    assert report["isolated"] == []

    see_people = next(row for row in report["occasions"] if row["occasion"] == "见人")
    assert see_people["best_formality"] == 2.5
    assert see_people["target"] == [3.5, 4.5]
    assert see_people["fit_rate"] == 0.0
    assert see_people["blocked_slots"] == [
        "base_top",
        "mid_layer",
        "outer_layer",
        "bottom",
        "shoes",
    ]

    assert report["fills"][0]["slot"] == "bottom"
    assert report["fills"][0]["total_unlock"] == 59
    assert report["fills"][0]["unlock"] == {
        "cold": 3,
        "cool": 14,
        "warm": 25,
        "hot": 17,
    }


@requires_real_db
def test_approximate_merge_is_not_monotone(real_case) -> None:
    """把 `V ∪ C_x` 的近似值接回展示层会少算，固定对照防止回归。"""
    items = real_case
    candidates, valid = _solve_bands(items)
    black = next(
        prototype
        for prototype in _prototypes(items, "bottom", max(item.id for item in items) + 1)
        if prototype.formality == 2
        and prototype.weight == "thin"
        and prototype.color_hex == "#141414"
    )
    grey = replace(black, color_hex="#6B7280")

    approximate: dict[str, int] = {}
    for band in BANDS:
        ctx = Context(occasion="日常", feels_like=band.feels_like)
        added = [
            assessment
            for candidate in enumerate_candidates([*items, grey], anchor=grey)
            if (assessment := assess(candidate, ctx)) is not None
            and assessment.level == 0
        ]
        merged = dedup(
            [*valid[band.key], *added],
            limit=len(valid[band.key]) + len(added),
        )
        approximate[band.key] = len(merged) - len(valid[band.key])

    exact = _unlock(grey, items, candidates, valid)

    assert approximate == {"cold": -1, "cool": 2, "warm": 25, "hot": 17}
    assert sum(approximate.values()) == 43
    assert exact == {"cold": 3, "cool": 14, "warm": 25, "hot": 17}
    assert sum(exact.values()) == 59
    assert approximate != exact
