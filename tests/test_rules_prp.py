"""比例与轮廓模块 4 条规则的单测。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Context, Status


def test_prp_01_fails_when_upper_and_lower_both_oversize() -> None:
    c = outfit(
        base=layer_item("base", fit="oversize"),
        bottom=layer_item("bottom", fit="oversize"),
    )
    hit = run_rule("R-PRP-01", c)
    assert hit.is_fail
    assert "上宽下也宽" in (hit.reason or "")


def test_prp_01_passes_when_only_upper_is_oversize() -> None:
    c = outfit(
        base=layer_item("base", fit="oversize"),
        bottom=layer_item("bottom", fit="regular"),
    )
    assert run_rule("R-PRP-01", c).status is Status.PASS


def test_prp_02_fails_when_upper_and_lower_both_slim() -> None:
    c = outfit(
        base=layer_item("base", fit="slim"),
        bottom=layer_item("bottom", fit="slim"),
    )
    hit = run_rule("R-PRP-02", c)
    assert hit.is_fail
    assert "上紧下也紧" in (hit.reason or "")


def test_prp_02_passes_when_only_upper_is_slim() -> None:
    c = outfit(
        base=layer_item("base", fit="slim"),
        bottom=layer_item("bottom", fit="regular"),
    )
    assert run_rule("R-PRP-02", c).status is Status.PASS


def test_prp_03_rewards_two_step_width_contrast() -> None:
    c = outfit(
        base=layer_item("base", fit="oversize"),
        bottom=layer_item("bottom", fit="slim"),
    )
    hit = run_rule("R-PRP-03", c)
    assert hit.is_scored
    assert hit.value == 2.0


def test_prp_03_skips_one_step_difference() -> None:
    c = outfit(
        base=layer_item("base", fit="oversize"),
        bottom=layer_item("bottom", fit="regular"),
    )
    assert run_rule("R-PRP-03", c).status is Status.SKIP


def test_prp_04_penalises_long_outer_on_short_person() -> None:
    c = outfit(
        outer=layer_item("outer", length_cm=90),
    )
    hit = run_rule("R-PRP-04", c, Context(height_cm=160))
    assert hit.is_scored
    assert hit.value == -1.0


def test_prp_04_skips_without_height() -> None:
    c = outfit(outer=layer_item("outer", length_cm=90))
    assert run_rule("R-PRP-04", c).status is Status.SKIP


def test_prp_04_skips_when_hem_is_above_the_ratio() -> None:
    # 160cm 的 0.55 是 88cm；80cm 的下摆不压身高
    c = outfit(outer=layer_item("outer", length_cm=80))
    assert run_rule("R-PRP-04", c, Context(height_cm=160)).status is Status.SKIP
