"""层次模块 3 条规则的单测，含 R-LYR-01 的放宽档位行为。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Status


def test_lyr_01_fails_when_outer_is_thinner_than_inner() -> None:
    c = outfit(
        base=layer_item("base", weight="thick"),
        outer=layer_item("outer", weight="thin"),
    )
    hit = run_rule("R-LYR-01", c)
    assert hit.is_fail
    assert "厚度倒挂" in (hit.reason or "")


def test_lyr_01_passes_when_thickness_grows_outward() -> None:
    c = outfit(
        base=layer_item("base", weight="thin"),
        outer=layer_item("outer", weight="thick"),
    )
    assert run_rule("R-LYR-01", c).status is Status.PASS


def test_lyr_01_relaxes_only_at_the_top_tier() -> None:
    # 外层比内层薄一级：档位 1/2 仍判失败，档位 3（tol=2.0）才放行
    c = outfit(
        base=layer_item("base", weight="thick"),
        outer=layer_item("outer", weight="medium"),
    )
    assert run_rule("R-LYR-01", c, tol=1.0).is_fail
    assert run_rule("R-LYR-01", c, tol=2.0).status is Status.PASS


def test_lyr_02_rewards_clear_length_steps() -> None:
    c = outfit(
        base=layer_item("base", length_cm=60),
        mid=layer_item("mid", length_cm=68),
        outer=layer_item("outer", length_cm=75),
    )
    hit = run_rule("R-LYR-02", c)
    assert hit.is_scored
    assert hit.value == 1.5


def test_lyr_02_skips_when_lengths_are_too_close() -> None:
    c = outfit(
        base=layer_item("base", length_cm=60),
        mid=layer_item("mid", length_cm=62),
        outer=layer_item("outer", length_cm=64),
    )
    assert run_rule("R-LYR-02", c).status is Status.SKIP


def test_lyr_02_skips_when_length_missing() -> None:
    c = outfit(
        base=layer_item("base", length_cm=None),
        mid=layer_item("mid", length_cm=68),
        outer=layer_item("outer", length_cm=75),
    )
    assert run_rule("R-LYR-02", c).status is Status.SKIP


def test_lyr_03_penalises_repeated_hood() -> None:
    c = outfit(
        base=layer_item("base", collar="连帽"),
        outer=layer_item("outer", collar="连帽"),
    )
    hit = run_rule("R-LYR-03", c)
    assert hit.is_scored
    assert hit.value == -1.5


def test_lyr_03_skips_different_collars() -> None:
    c = outfit(
        base=layer_item("base", collar="翻领"),
        outer=layer_item("outer", collar="高领"),
    )
    assert run_rule("R-LYR-03", c).status is Status.SKIP


def test_lyr_03_ignores_non_repeating_collar_types() -> None:
    # 两个翻领不算「领型重复」——只有高领/连帽会叠加
    c = outfit(
        base=layer_item("base", collar="翻领"),
        outer=layer_item("outer", collar="翻领"),
    )
    assert run_rule("R-LYR-03", c).status is Status.SKIP
