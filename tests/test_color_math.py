"""色彩换算的基准测试。

色彩是整个规则引擎的地基：色差算错，COL/LYR/SHO 三层判定一起失真。
这里锁死两类基准——CIELAB 的标准参考值，以及 `02` 第五节定下的分类口径。
"""

from __future__ import annotations

import pytest

from src.rules.color_math import (
    color_attrs,
    delta_e_hex,
    hex_to_rgb,
    hue_family,
    is_neutral,
    rgb_to_lab,
    warmth_of,
)


def test_hex_to_rgb_expands_shorthand() -> None:
    assert hex_to_rgb("#FFF") == (255, 255, 255)
    assert hex_to_rgb("808080") == (128, 128, 128)
    assert hex_to_rgb("#c0392b") == (192, 57, 43)


@pytest.mark.parametrize("bad", ["", "#12", "#GGGGGG", "#12345", "red"])
def test_hex_to_rgb_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ValueError):
        hex_to_rgb(bad)


def test_rgb_to_lab_matches_srgb_d65_reference() -> None:
    # 标准参考值：红 (53.24, 80.09, 67.20)；白 L=100；黑全零
    assert rgb_to_lab((255, 0, 0)) == pytest.approx((53.241, 80.092, 67.203), abs=0.01)
    assert rgb_to_lab((255, 255, 255)) == pytest.approx((100.0, 0.0, 0.0), abs=0.01)
    assert rgb_to_lab((0, 0, 0)) == pytest.approx((0.0, 0.0, 0.0), abs=0.01)


def test_delta_e_hex_identity_and_symmetry() -> None:
    assert delta_e_hex("#808080", "#808080") == 0.0
    assert delta_e_hex("#1E829B", "#37829B") == pytest.approx(
        delta_e_hex("#37829B", "#1E829B")
    )


def test_delta_e_hex_matches_ciede2000_scale() -> None:
    # 红 vs 绿 的 CIEDE2000 约 86.6，远大于「糊在一起」的阈值 10
    assert delta_e_hex("#FF0000", "#00FF00") == pytest.approx(86.608, abs=0.01)
    assert delta_e_hex("#1E829B", "#37829B") == pytest.approx(2.139, abs=0.01)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#C0392B", "红"),
        ("#F1C40F", "黄"),
        ("#27AE60", "绿"),
        ("#1F6FEB", "蓝"),
        ("#1E829B", "青"),
        ("#808080", "中性"),
    ],
)
def test_hue_family_bands(value: str, expected: str) -> None:
    attrs = color_attrs(value)
    assert hue_family(attrs.hue, attrs.saturation, attrs.lightness) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#808080", True),   # 灰
        ("#1F3A5F", True),   # 藏青：蓝但足够暗、饱和度不爆
        ("#222A37", True),   # 深蓝牛仔，同样按藏青处理
        ("#C0392B", False),  # 红
        ("#F1C40F", False),  # 黄
    ],
)
def test_is_neutral(value: str, expected: bool) -> None:
    attrs = color_attrs(value)
    assert is_neutral(attrs.hue, attrs.saturation, attrs.lightness) is expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#C0392B", "warm"),
        ("#F1C40F", "warm"),
        ("#1F6FEB", "cool"),
        ("#1E829B", "cool"),
        ("#808080", "neutral"),
        # 绿落在 90–165 的过渡带，既不判暖也不判冷（COL-04 因此不拿绿色做冲突源）
        ("#27AE60", "neutral"),
    ],
)
def test_warmth(value: str, expected: str) -> None:
    attrs = color_attrs(value)
    assert warmth_of(attrs.hue, attrs.saturation, attrs.is_neutral) == expected


def test_main_color_and_high_sat_thresholds() -> None:
    assert color_attrs("#7FB3E8").is_main_color is True   # 低饱和但有彩度
    assert color_attrs("#1F3A5F").is_main_color is False  # 藏青算中性色
    assert color_attrs("#808080").is_main_color is False  # 无彩度
    assert color_attrs("#1F6FEB").is_high_sat is True
    assert color_attrs("#7FB3E8").is_high_sat is False
