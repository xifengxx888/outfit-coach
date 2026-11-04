"""图案模块 2 条规则的单测。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Status


def test_pat_01_fails_with_two_bold_patterns() -> None:
    c = outfit(
        base=layer_item("base", pattern="bold"),
        bottom=layer_item("bottom", pattern="bold"),
    )
    hit = run_rule("R-PAT-01", c)
    assert hit.is_fail
    assert "2 件" in (hit.reason or "")


def test_pat_01_passes_with_one_bold_pattern() -> None:
    c = outfit(base=layer_item("base", pattern="bold"))
    assert run_rule("R-PAT-01", c).status is Status.PASS


def test_pat_02_rewards_pattern_on_the_bottom() -> None:
    c = outfit(bottom=layer_item("bottom", pattern="bold"))
    hit = run_rule("R-PAT-02", c)
    assert hit.is_scored
    assert hit.value == 1.0


def test_pat_02_skips_pattern_in_a_non_visual_slot() -> None:
    # 图案落在内搭上，视觉主体位（外套/下装）没有图案 → 不加分
    c = outfit(base=layer_item("base", pattern="bold"))
    assert run_rule("R-PAT-02", c).status is Status.SKIP


def test_pat_02_skips_when_another_piece_is_not_solid() -> None:
    c = outfit(
        base=layer_item("base", pattern="fine"),
        bottom=layer_item("bottom", pattern="bold"),
    )
    assert run_rule("R-PAT-02", c).status is Status.SKIP
