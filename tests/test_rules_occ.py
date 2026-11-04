"""场合与温度模块 3 条规则的单测，覆盖四个温度区间与放宽跨边界。"""

from __future__ import annotations

import pytest

from factories import layer_item, outfit, run_rule
from src.rules.occ import target_warmth
from src.rules.types import Context, Status


def test_occ_01_skips_without_feels_like() -> None:
    assert run_rule("R-OCC-01", outfit()).status is Status.SKIP


def test_occ_01_passes_thin_single_layer_when_hot() -> None:
    assert run_rule("R-OCC-01", outfit(), Context(feels_like=28)).status is Status.PASS


def test_occ_01_fails_when_hot_but_wearing_an_outer() -> None:
    c = outfit(outer=layer_item("outer", weight="thin"))
    assert run_rule("R-OCC-01", c, Context(feels_like=28)).is_fail


def test_occ_01_passes_thin_outer_in_mild_weather() -> None:
    c = outfit(outer=layer_item("outer", weight="thin"))
    assert run_rule("R-OCC-01", c, Context(feels_like=15)).status is Status.PASS


def test_occ_01_fails_with_base_only_in_mild_weather() -> None:
    assert run_rule("R-OCC-01", outfit(), Context(feels_like=15)).is_fail


def test_occ_01_passes_three_layers_when_cold() -> None:
    c = outfit(
        base=layer_item("base", weight="thin"),
        mid=layer_item("mid", weight="medium"),
        outer=layer_item("outer", weight="thick"),
    )
    assert run_rule("R-OCC-01", c, Context(feels_like=5)).status is Status.PASS


def test_occ_01_fails_with_thin_layers_when_cold() -> None:
    c = outfit(
        base=layer_item("base", weight="thin"),
        mid=layer_item("mid", weight="thin"),
        outer=layer_item("outer", weight="thin"),
    )
    assert run_rule("R-OCC-01", c, Context(feels_like=5)).is_fail


def test_occ_01_relaxation_lets_a_thin_outer_through_near_26c() -> None:
    # 26.2°C 严格按「≥26°C 只穿内层」判失败；放宽 0.5 后跨回 26°C 边界内，放行
    c = outfit(outer=layer_item("outer", weight="thin"))
    ctx = Context(feels_like=26.2)
    assert run_rule("R-OCC-01", c, ctx, tol=0.0).is_fail
    assert run_rule("R-OCC-01", c, ctx, tol=0.5).status is Status.PASS


def test_occ_02_rewards_daily_formality() -> None:
    hit = run_rule("R-OCC-02", outfit(), Context(occasion="日常"))
    assert hit.is_scored
    assert hit.value == 2.0


def test_occ_02_rewards_meeting_formality() -> None:
    c = outfit(
        base=layer_item("base", formality=4),
        bottom=layer_item("bottom", formality=4),
        shoes=layer_item("shoes", formality=4),
    )
    hit = run_rule("R-OCC-02", c, Context(occasion="见人"))
    assert hit.is_scored
    assert hit.value == 2.0


def test_occ_02_skips_when_formality_is_far_off() -> None:
    c = outfit(
        base=layer_item("base", formality=5),
        bottom=layer_item("bottom", formality=5),
        shoes=layer_item("shoes", formality=5),
    )
    assert run_rule("R-OCC-02", c, Context(occasion="日常")).status is Status.SKIP


def test_occ_03_rewards_matching_warmth() -> None:
    # 30°C 目标暖度 1.0，内搭+下装都是薄款 → 正好命中
    hit = run_rule("R-OCC-03", outfit(), Context(feels_like=30))
    assert hit.is_scored
    assert hit.value == 1.5


def test_occ_03_skips_when_warmth_is_off_target() -> None:
    # 22°C 目标约 2.14，全身仍只有薄款（1.0）→ 不加分
    assert run_rule("R-OCC-03", outfit(), Context(feels_like=22)).status is Status.SKIP


def test_occ_03_skips_without_feels_like() -> None:
    assert run_rule("R-OCC-03", outfit()).status is Status.SKIP


@pytest.mark.parametrize(
    ("feels_like", "expected"),
    [(30.0, 1.0), (23.0, 2.0), (2.0, 5.0), (-10.0, 5.5)],
)
def test_target_warmth_clamps_to_1_through_5_5(
    feels_like: float, expected: float
) -> None:
    assert target_warmth(feels_like) == pytest.approx(expected)
