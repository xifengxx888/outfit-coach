"""色彩模块 6 条规则的单测（每条至少一个触发、一个不触发）。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Status

RED = "#C0392B"      # 红、高饱和、暖
BLUE = "#1F6FEB"     # 蓝、高饱和、冷
GREEN = "#27AE60"    # 绿、高饱和、冷暖过渡带
YELLOW = "#F1C40F"   # 黄、高饱和、暖
CYAN = "#1E829B"     # 青
BLUE2 = "#37829B"    # 蓝，与 CYAN 视觉几乎同色
SKY = "#7FB3E8"      # 浅蓝
NAVY = "#1F3A5F"     # 藏青（算中性色）


def test_col_01_fails_when_four_main_colours() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        outer=layer_item("outer", color_hex=BLUE),
        bottom=layer_item("bottom", color_hex=GREEN),
        shoes=layer_item("shoes", color_hex=YELLOW),
    )
    hit = run_rule("R-COL-01", c)
    assert hit.is_fail
    assert "4 个" in (hit.reason or "")


def test_col_01_passes_when_three_main_colours() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        outer=layer_item("outer", color_hex=BLUE),
        bottom=layer_item("bottom", color_hex=GREEN),
    )
    assert run_rule("R-COL-01", c).status is Status.PASS


def test_col_02_penalises_near_identical_cross_family_colours() -> None:
    # 青 vs 蓝：视觉上糊成一片，但色系判定不同 → 扣 2 分
    c = outfit(
        base=layer_item("base", color_hex=CYAN),
        outer=layer_item("outer", color_hex=BLUE2),
    )
    hit = run_rule("R-COL-02", c)
    assert hit.is_scored
    assert hit.value == -2.0


def test_col_02_skips_colours_in_the_same_family() -> None:
    assert run_rule("R-COL-02", outfit()).status is Status.SKIP


def test_col_03_rewards_same_family_with_depth() -> None:
    c = outfit(
        base=layer_item("base", color_hex=SKY),
        outer=layer_item("outer", color_hex=NAVY),
    )
    hit = run_rule("R-COL-03", c)
    assert hit.is_scored
    assert hit.value == 2.0


def test_col_03_skips_when_too_close_in_lightness() -> None:
    # 同色系但色差 < 10，看不出层次，不加分
    c = outfit(
        base=layer_item("base", color_hex=BLUE2),
        outer=layer_item("outer", color_hex="#37829D"),
    )
    assert run_rule("R-COL-03", c).status is Status.SKIP


def test_col_04_fails_when_high_sat_cool_meets_high_sat_warm() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        shoes=layer_item("shoes", color_hex=BLUE),
    )
    hit = run_rule("R-COL-04", c)
    assert hit.is_fail
    assert "高饱和冷色" in (hit.reason or "")


def test_col_04_passes_when_both_high_sat_colours_are_warm() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        shoes=layer_item("shoes", color_hex=YELLOW),
    )
    assert run_rule("R-COL-04", c).status is Status.PASS


def test_col_05_penalises_saturation_overload() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        outer=layer_item("outer", color_hex=BLUE),
        bottom=layer_item("bottom", color_hex=GREEN),
    )
    hit = run_rule("R-COL-05", c)
    assert hit.is_scored
    assert hit.value == -1.5


def test_col_05_skips_neutral_outfit() -> None:
    assert run_rule("R-COL-05", outfit()).status is Status.SKIP


def test_col_06_rewards_a_neutral_anchor() -> None:
    hit = run_rule("R-COL-06", outfit())
    assert hit.is_scored
    assert hit.value == 1.5


def test_col_06_skips_when_every_body_item_is_coloured() -> None:
    c = outfit(
        base=layer_item("base", color_hex=RED),
        bottom=layer_item("bottom", color_hex=GREEN),
        shoes=layer_item("shoes", color_hex=YELLOW),
    )
    assert run_rule("R-COL-06", c).status is Status.SKIP
