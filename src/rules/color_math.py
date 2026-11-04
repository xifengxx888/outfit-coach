"""色彩换算：HEX → Lab / HSV，CIEDE2000 色差，色系与中性色判定。

规则引擎只认 `color_hex` 一个源，其余色彩属性全部由它派生（见 `ColorAttrs`），
避免数据库里的 `hue_family` / `saturation` 与 `color_hex` 对不上。

口径与 `08` 量衣教程、`scripts/spike/dryrun.py` 完全一致：
- 明度 L 取 Lab 的 L*（0–100），不是 HSV 的 V
- 饱和度 S 取 HSV 的 S（0–100）
- 色相 H 取 HSV 的 H（0–360）
- ΔE00 用 `colour.difference.delta_E_CIE2000`（02 第五节规定）
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from colour.difference import delta_E_CIE2000

# 色系边界（02 第五节「色彩实现口径」）
HUE_BANDS = (
    (345.0, 360.0, "红"),
    (0.0, 15.0, "红"),
    (15.0, 45.0, "橙"),
    (45.0, 70.0, "黄"),
    (70.0, 165.0, "绿"),
    (165.0, 195.0, "青"),
    (195.0, 255.0, "蓝"),
    (255.0, 345.0, "紫"),
)

# 中性色阈值（黑/白/灰 + 藏青 + 卡其/米）
NEUTRAL_SAT = 12.0
NEUTRAL_BLACK_L = 10.0
NEUTRAL_WHITE_L = 92.0
NAVY = {"hue": (195.0, 245.0), "max_l": 38.0, "max_s": 70.0}
KHAKI = {"hue": (20.0, 60.0), "max_s": 50.0, "l": (55.0, 88.0)}

# 判定「主色」的最低饱和度（02：低饱和色不算主色）
MAIN_COLOR_MIN_SAT = 15.0
# 判定「高饱和」的阈值（R-COL-04）
HIGH_SAT = 60.0


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    """`#RRGGBB` 或 `#RGB` → (r, g, b)。格式不对直接抛 ValueError。"""
    h = (value or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"颜色不是 #RRGGBB：{value!r}")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    """sRGB(D65) → CIELAB。"""
    r, g, b = (v / 255.0 for v in rgb)

    def linearize(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = linearize(r), linearize(g), linearize(b)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / 1.00000
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)

    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


@lru_cache(maxsize=None)
def delta_e_hex(hex1: str, hex2: str) -> float:
    """两种颜色的 CIEDE2000 色差。"""
    lab1, lab2 = rgb_to_lab(hex_to_rgb(hex1)), rgb_to_lab(hex_to_rgb(hex2))
    return float(delta_E_CIE2000(np.array(lab1), np.array(lab2)))


def hue_family(hue: float, sat: float, light: float) -> str:
    if sat < NEUTRAL_SAT or light < 8:
        return "中性"
    for lo, hi, name in HUE_BANDS:
        if lo <= hue < hi:
            return name
    return "中性"


def is_neutral(hue: float, sat: float, light: float) -> bool:
    """中性色：黑/白/灰、藏青、卡其/米。"""
    if sat < NEUTRAL_SAT:
        return True
    if light < NEUTRAL_BLACK_L or light > NEUTRAL_WHITE_L:
        return True
    if NAVY["hue"][0] <= hue <= NAVY["hue"][1] and light <= NAVY["max_l"] and sat <= NAVY["max_s"]:
        return True
    if (
        KHAKI["hue"][0] <= hue <= KHAKI["hue"][1]
        and sat <= KHAKI["max_s"]
        and KHAKI["l"][0] <= light <= KHAKI["l"][1]
    ):
        return True
    return False


def warmth_of(hue: float, sat: float, neutral: bool) -> str:
    """冷暖。中性色一律 neutral；色相决定冷暖。"""
    if neutral:
        return "neutral"
    if 165 <= hue <= 285:
        return "cool"
    if hue < 90 or hue >= 330:
        return "warm"
    return "neutral"


@dataclass(frozen=True)
class ColorAttrs:
    lab: tuple[float, float, float]
    hue: float
    saturation: float
    lightness: float
    hue_family: str
    is_neutral: bool
    warmth: str

    @property
    def is_main_color(self) -> bool:
        """算不算「主色」：有彩度且非中性色。"""
        return (not self.is_neutral) and self.saturation >= MAIN_COLOR_MIN_SAT

    @property
    def is_high_sat(self) -> bool:
        return self.saturation >= HIGH_SAT


def color_attrs(color_hex: str) -> ColorAttrs:
    """由 `#RRGGBB` 派生全部色彩属性。"""
    rgb = hex_to_rgb(color_hex)
    lab = rgb_to_lab(rgb)
    h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    hue, sat = h * 360.0, s * 100.0
    light = lab[0]
    family = hue_family(hue, sat, light)
    neutral = is_neutral(hue, sat, light)
    return ColorAttrs(
        lab=lab,
        hue=hue,
        saturation=sat,
        lightness=light,
        hue_family=family,
        is_neutral=neutral,
        warmth=warmth_of(hue, sat, neutral),
    )


__all__ = [
    "ColorAttrs",
    "HIGH_SAT",
    "MAIN_COLOR_MIN_SAT",
    "color_attrs",
    "delta_e_hex",
    "hex_to_rgb",
    "hue_family",
    "is_neutral",
    "rgb_to_lab",
    "warmth_of",
]
