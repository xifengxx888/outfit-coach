"""轮换修正单测：近期穿过扣分、久未穿加分、swap 衰减，以及只改排序不改合规。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from factories import layer_item, outfit
from src.rules.identity import outfit_hash
from src.rules.rotation import (
    FRESH_BONUS,
    RECENT_PENALTY,
    Rotation,
    build_rotation,
    parse_day,
    recency_adjustment,
    swap_penalty,
)
from src.rules.solver import Assessment, rank_key, solve
from src.rules.types import Context

TODAY = date(2026, 10, 26)


def _assessment(candidate, level: int, score: float) -> Assessment:
    return Assessment(
        candidate=candidate,
        level=level,
        relaxed_rules=(),
        score=score,
        soft_hits=(),
        reason="",
    )


# ---------------------------------------------------------------------------
# 单件修正
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (None, FRESH_BONUS),          # 从没穿过
        (0, RECENT_PENALTY),          # 今天
        (1, RECENT_PENALTY),          # 昨天
        (2, -1.0),                    # 前天
        (3, -1.0),
        (4, 0.03),                    # 开始回正
        (12, 0.25),
        (21, FRESH_BONUS),            # 到顶
        (40, FRESH_BONUS),
        (-5, RECENT_PENALTY),         # 未来日期按今天处理，不给加分
    ],
)
def test_recency_adjustment_tiers(days_ago: int | None, expected: float) -> None:
    last_worn = None if days_ago is None else TODAY - timedelta(days=days_ago)
    assert recency_adjustment(last_worn, TODAY) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("days_ago", "expected"),
    [
        (0, -4.0),
        (7, -2.0),
        (13, -0.29),
        (14, 0.0),
        (30, 0.0),
        (-1, -4.0),  # 未来日期同样按最近一次处理
    ],
)
def test_swap_penalty_decays_linearly(days_ago: int, expected: float) -> None:
    assert swap_penalty(TODAY - timedelta(days=days_ago), TODAY) == pytest.approx(
        expected
    )


def test_parse_day_tolerates_dirty_values() -> None:
    assert parse_day("2026-10-26") == TODAY
    assert parse_day(None) is None
    assert parse_day("") is None
    assert parse_day("2026-13-01") is None
    assert parse_day("昨天") is None


# ---------------------------------------------------------------------------
# 组合修正
# ---------------------------------------------------------------------------


def test_rotation_delta_sums_items_and_swap() -> None:
    rotation = Rotation(
        item_adjustments={1: -2.5, 2: 0.5},
        swap_penalties={outfit_hash([1, 2, 3]): -4.0},
    )
    assert rotation.delta([1, 2, 3]) == pytest.approx(-6.0)
    assert rotation.delta([1, 2]) == pytest.approx(-2.0)
    assert rotation.delta([9]) == 0.0


def test_build_rotation_uses_last_worn_and_keeps_heaviest_swap() -> None:
    items = [
        layer_item("base", id=1, last_worn_at=TODAY.isoformat()),
        layer_item("bottom", id=2, last_worn_at=(TODAY - timedelta(days=10)).isoformat()),
        layer_item("shoes", id=3, last_worn_at="不是日期"),
    ]
    target = outfit_hash([1, 2, 3])
    expired = outfit_hash([4, 5, 6])
    rotation = build_rotation(
        items,
        [
            (TODAY, target),
            (TODAY - timedelta(days=10), target),
            (TODAY - timedelta(days=20), expired),
        ],
        TODAY,
    )

    assert rotation.item_adjustments == {1: -2.5, 2: 0.19, 3: FRESH_BONUS}
    assert rotation.swap_penalties == {target: -4.0}


# ---------------------------------------------------------------------------
# 只重排，不放行
# ---------------------------------------------------------------------------


def test_rotation_reorders_within_the_same_level() -> None:
    low = _assessment(outfit(bottom=layer_item("bottom", id=21)), 0, 1.0)
    high = _assessment(outfit(bottom=layer_item("bottom", id=22)), 0, 9.0)
    rotation = Rotation(item_adjustments={21: 10.0})

    assert sorted([low, high], key=rank_key) == [high, low]
    assert sorted([low, high], key=lambda a: rank_key(a, rotation)) == [low, high]


def test_rotation_never_crosses_levels() -> None:
    strict = _assessment(outfit(bottom=layer_item("bottom", id=21)), 0, -20.0)
    relaxed = _assessment(outfit(bottom=layer_item("bottom", id=22)), 1, 99.0)
    rotation = Rotation(item_adjustments={21: 100.0})

    assert sorted([relaxed, strict], key=lambda a: rank_key(a, rotation)) == [
        strict,
        relaxed,
    ]


def test_rotation_never_rescues_hard_rejected_outfit() -> None:
    items = [
        layer_item("base", id=1),
        layer_item("bottom", id=2),
        layer_item("shoes", id=3),
        layer_item("base", id=4, pattern="bold"),
        layer_item("bottom", id=5, pattern="bold"),
    ]
    rotation = Rotation(item_adjustments={item.id: 50.0 for item in items})

    result = solve(items, Context(), limit=10, rotation=rotation)
    ids = [set(assessment.garment_ids) for assessment in result.outfits]

    assert {1, 2, 3} in ids
    assert {4, 2, 3} in ids
    assert {1, 5, 3} in ids
    assert {4, 5, 3} not in ids
