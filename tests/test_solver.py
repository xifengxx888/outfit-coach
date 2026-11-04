"""求解器单测：档位优先、放宽扣分、去重与锚定。"""

from __future__ import annotations

import pytest

from factories import layer_item, outfit
from src.rules.registry import evaluate_soft
from src.rules.solver import (
    RELAX_PENALTY,
    Assessment,
    assess,
    dedup,
    rank_key,
    solve,
)
from src.rules.types import Context


def _assessment(ids_outfit, level: int, score: float) -> Assessment:
    return Assessment(
        candidate=ids_outfit,
        level=level,
        relaxed_rules=(),
        score=score,
        soft_hits=(),
        reason="",
    )


def test_clean_outfit_passes_at_strict_tier() -> None:
    result = assess(outfit(), Context())
    assert result is not None
    assert result.level == 0
    assert result.relaxed_rules == ()


def test_thickness_violation_only_passes_at_tier_three() -> None:
    c = outfit(
        base=layer_item("base", weight="thick"),
        outer=layer_item("outer", weight="medium"),
    )
    result = assess(c, Context())
    assert result is not None
    assert result.level == 3
    assert result.relaxed_rules == ("R-LYR-01",)
    soft_sum = sum(h.value for h in evaluate_soft(c, Context()) if h.is_scored)
    assert result.score == pytest.approx(soft_sum - RELAX_PENALTY[3])


def test_temperature_violation_relaxes_at_the_first_tier() -> None:
    c = outfit(outer=layer_item("outer", weight="thin"))
    result = assess(c, Context(feels_like=26.2))
    assert result is not None
    assert result.level == 1
    assert result.relaxed_rules == ("R-OCC-01",)


def test_relationship_violation_is_never_accepted() -> None:
    c = outfit(
        base=layer_item("base", pattern="bold"),
        bottom=layer_item("bottom", pattern="bold"),
    )
    assert assess(c, Context()) is None


def test_rank_prefers_strict_tier_over_higher_score() -> None:
    strict_low = _assessment(outfit(bottom=layer_item("bottom", id=21)), 0, 1.0)
    relaxed_high = _assessment(outfit(bottom=layer_item("bottom", id=22)), 1, 99.0)
    assert sorted([relaxed_high, strict_low], key=rank_key) == [
        strict_low,
        relaxed_high,
    ]


def test_rank_uses_score_within_the_same_tier() -> None:
    low = _assessment(outfit(bottom=layer_item("bottom", id=21)), 0, 1.0)
    high = _assessment(outfit(bottom=layer_item("bottom", id=22)), 0, 9.0)
    assert sorted([low, high], key=rank_key) == [high, low]


def test_dedup_drops_outfits_sharing_three_items() -> None:
    shared_outer = layer_item("outer", id=5)
    first = _assessment(
        outfit(outer=shared_outer, bottom=layer_item("bottom", id=21)), 0, 10.0
    )
    second = _assessment(
        outfit(outer=shared_outer, bottom=layer_item("bottom", id=22)), 0, 5.0
    )
    kept = dedup([second, first])
    assert kept == [first]


def test_dedup_respects_limit() -> None:
    candidates = [
        _assessment(outfit(bottom=layer_item("bottom", id=20 + i)), 0, 1.0)
        for i in range(4)
    ]
    assert len(dedup(candidates, limit=2)) == 2


def test_solve_enumerates_and_ranks_deterministically() -> None:
    items = [
        layer_item("base"),
        layer_item("base", id=12, name="红色T恤", color_hex="#C0392B"),
        layer_item("bottom"),
        layer_item("shoes"),
        layer_item("outer"),
    ]
    first = solve(items, Context())
    second = solve(items, Context())

    assert first.candidate_count == 4
    assert first.best_level == 0
    assert all(a.level == 0 for a in first.outfits)
    assert first.outfits == tuple(sorted(first.outfits, key=rank_key))
    assert [a.garment_ids for a in first.outfits] == [
        a.garment_ids for a in second.outfits
    ]


def test_solve_with_anchor_only_returns_combinations_containing_it() -> None:
    red_base = layer_item("base", id=12, name="红色T恤", color_hex="#C0392B")
    items = [
        layer_item("base"),
        red_base,
        layer_item("bottom"),
        layer_item("shoes"),
        layer_item("outer"),
    ]
    result = solve(items, Context(), anchor=red_base)
    assert result.candidate_count == 2
    assert all(red_base.id in a.garment_ids for a in result.outfits)


def test_solve_reports_all_rejected_when_nothing_survives() -> None:
    items = [
        layer_item("base", pattern="bold"),
        layer_item("bottom", pattern="bold"),
        layer_item("shoes"),
    ]
    result = solve(items, Context())
    assert result.candidate_count == 1
    assert result.all_rejected is True
    assert result.best_level is None
