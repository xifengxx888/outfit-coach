"""正式度模块 2 条硬规则的单测。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Status


def test_frm_01_fails_when_adjacent_layers_jump_two_levels() -> None:
    c = outfit(
        base=layer_item("base", formality=3),
        outer=layer_item("outer", formality=5),
    )
    hit = run_rule("R-FRM-01", c)
    assert hit.is_fail
    assert "正式度差 2" in (hit.reason or "")


def test_frm_01_passes_when_adjacent_gap_is_one() -> None:
    c = outfit(
        base=layer_item("base", formality=3),
        outer=layer_item("outer", formality=4),
    )
    assert run_rule("R-FRM-01", c).status is Status.PASS


def test_frm_02_fails_when_whole_outfit_spread_exceeds_two() -> None:
    c = outfit(
        base=layer_item("base", formality=1),
        bottom=layer_item("bottom", formality=4),
    )
    hit = run_rule("R-FRM-02", c)
    assert hit.is_fail
    assert "极差 3" in (hit.reason or "")


def test_frm_02_passes_at_spread_two() -> None:
    c = outfit(
        base=layer_item("base", formality=2),
        bottom=layer_item("bottom", formality=4),
    )
    assert run_rule("R-FRM-02", c).status is Status.PASS
