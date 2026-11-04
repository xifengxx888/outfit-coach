#!/usr/bin/env python3
"""M1 开工前一次性干跑：槽位枚举 + 24 条规则 + 渐进放宽 + 多样性去重 + 锚定。

**不进 src/。** 不接数据库、不接前端、不调模型。目的只有一个：
在真实单品上验证 02 第五节的规则与阈值是否成立。

用法：
  python3 scripts/spike/dryrun.py --items scripts/spike/items_template.xlsx
  python3 scripts/spike/dryrun.py --items scripts/spike/items_demo.csv
  python3 scripts/spike/dryrun.py --items scripts/spike/items_edge.csv \
      --feels-like 8 --rain --height 160
  python3 scripts/spike/dryrun.py --items scripts/spike/items.csv \
      --occasion 日常 --feels-like 15 --rain --height 175

输入可以是 xlsx（读「填写」工作表，填完直接跑，不用另存 CSV）
或 CSV（UTF-8）。列定义见「填写说明」。
输出：
  - 终端摘要：各档组合数、硬/软规则健康度、每档新增前 10 套、锚定结果、验收勾选
  - scripts/spike/dryrun_result.json：完整结果（每档新增与累计各前 10），供人工复核

注意：这是 spike，不是生产实现。规则函数故意写成单文件、无依赖，
      方便逐条对照 02 第五节；生产实现要拆到 src/rules/ 并补单测。
"""

from __future__ import annotations

import argparse
import colorsys
import csv
import json
import math
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量与枚举
# ---------------------------------------------------------------------------

LAYER_TO_SLOT = {
    "inner": "base_top",
    "mid": "mid_layer",
    "outer": "outer_layer",
    "bottom": "bottom",
    "shoes": "shoes",
    "accessory": "accessory",
}
SLOT_ORDER = ["base_top", "mid_layer", "outer_layer", "bottom", "shoes", "accessory"]
REQUIRED_SLOTS = {"base_top", "bottom", "shoes"}

CATEGORY_SLOTS = {
    "连体装": ("base_top", "bottom"),
    "西装套装": ("outer_layer", "bottom"),
}
BOTTOM_CATEGORIES = {"裤子", "牛仔裤", "短裤"}

KNOWN_CATEGORIES = {
    "T恤", "衬衫", "卫衣", "毛衣", "针织", "外套", "夹克", "西装",
    "裤子", "牛仔裤", "短裤", "鞋", "配饰", "连体装", "西装套装",
}

WEIGHT_IDX = {"thin": 1, "medium": 2, "thick": 3}
# 暖度分：把三档厚度映射到 OCC-03 的 1–5 目标尺度
WARMTH = {"thin": 1.0, "medium": 3.0, "thick": 5.0}
FIT_IDX = {"slim": 1, "regular": 2, "oversize": 3}
FIT_CN = {"slim": "修身", "regular": "合身", "oversize": "宽松"}

STIFF_MATERIALS = {"牛仔", "皮革", "尼龙", "羊毛", "帆布", "防水涂层"}
SOFT_MATERIALS = {"棉", "针织", "亚麻", "化纤", "缎面", "麂皮"}
RAIN_BAD = {"麂皮", "帆布", "缎面"}
RAIN_GOOD = {"皮革", "橡胶", "防水涂层"}

ENUM_SYNONYMS = {
    # 版型
    "修身": "slim", "合身": "regular", "宽松": "oversize", "常规": "regular",
    # 图案
    "纯色": "solid", "细纹": "fine", "大图案": "bold", "大花纹": "bold",
    # 厚度
    "薄": "thin", "中": "medium", "中等": "medium", "厚": "thick",
    # 层级
    "内层": "inner", "中层": "mid", "外层": "outer",
    "下装": "bottom", "鞋": "shoes", "鞋子": "shoes", "配饰": "accessory",
    # 空值
    "不确定": "", "不适用": "", "无": "", "": "",
}

RULE_NAMES = {
    "R-COL-01": "主色 ≤3",
    "R-COL-02": "相邻层颜色糊在一起",
    "R-COL-03": "同色系深浅叠穿",
    "R-COL-04": "高饱和冷暖冲突",
    "R-COL-05": "全身饱和度过高",
    "R-COL-06": "中性色打底",
    "R-FRM-01": "相邻层正式度差 ≤1",
    "R-FRM-02": "全身正式度极差 ≤2",
    "R-PRP-01": "禁止上宽下宽",
    "R-PRP-02": "禁止上紧下紧",
    "R-PRP-03": "上宽下窄 / 上窄下宽",
    "R-PRP-04": "外套压身高",
    "R-LYR-01": "厚度逐层不减",
    "R-LYR-02": "三层长度差 ≥5cm",
    "R-LYR-03": "双层领型重复",
    "R-MAT-01": "相邻层材质对比",
    "R-PAT-01": "大图案 ≤1 件",
    "R-PAT-02": "图案在视觉主体位",
    "R-SHO-01": "鞋正式度与全身差 ≤1",
    "R-SHO-02": "鞋与上装/配饰同色系",
    "R-SHO-03": "降水时的鞋材质",
    "R-OCC-01": "厚度与温度区间兼容",
    "R-OCC-02": "场合正式度匹配",
    "R-OCC-03": "温度与暖度匹配",
}

# ---------------------------------------------------------------------------
# 颜色：sRGB → Lab → CIEDE2000
# ---------------------------------------------------------------------------


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"颜色不是 #RRGGBB：{value!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
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
    """CIEDE2000，与 colour.difference.delta_E_CIE2000 同式。"""
    lab1, lab2 = rgb_to_lab(hex_to_rgb(hex1)), rgb_to_lab(hex_to_rgb(hex2))
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2

    C1 = math.hypot(a1, b1)
    C2 = math.hypot(a2, b2)
    C_bar = (C1 + C2) / 2
    C_bar7 = C_bar ** 7
    G = 0.5 * (1 - math.sqrt(C_bar7 / (C_bar7 + 25 ** 7))) if C_bar7 else 0.0

    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def h_prime(a: float, b: float) -> float:
        if a == 0 and b == 0:
            return 0.0
        return math.degrees(math.atan2(b, a)) % 360

    h1p, h2p = h_prime(a1p, b1), h_prime(a2p, b2)
    dLp = L2 - L1
    dCp = C2p - C1p

    if C1p * C2p == 0:
        dhp = 0.0
    else:
        dhp = h2p - h1p
        if dhp > 180:
            dhp -= 360
        elif dhp < -180:
            dhp += 360
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp / 2))

    L_bar = (L1 + L2) / 2
    C_bar_p = (C1p + C2p) / 2
    if C1p * C2p == 0:
        h_bar_p = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar_p = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_bar_p = (h1p + h2p + 360) / 2
    else:
        h_bar_p = (h1p + h2p - 360) / 2

    T = (
        1
        - 0.17 * math.cos(math.radians(h_bar_p - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar_p))
        + 0.32 * math.cos(math.radians(3 * h_bar_p + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar_p - 63))
    )
    d_theta = 30 * math.exp(-(((h_bar_p - 275) / 25) ** 2))
    C_bar_p7 = C_bar_p ** 7
    Rc = 2 * math.sqrt(C_bar_p7 / (C_bar_p7 + 25 ** 7)) if C_bar_p7 else 0.0
    Sl = 1 + 0.015 * (L_bar - 50) ** 2 / math.sqrt(20 + (L_bar - 50) ** 2)
    Sc = 1 + 0.045 * C_bar_p
    Sh = 1 + 0.015 * C_bar_p * T
    Rt = -math.sin(math.radians(2 * d_theta)) * Rc

    return math.sqrt(
        (dLp / Sl) ** 2
        + (dCp / Sc) ** 2
        + (dHp / Sh) ** 2
        + Rt * (dCp / Sc) * (dHp / Sh)
    )


def hue_family(hue: float, sat: float, light: float) -> str:
    if sat < 12 or light < 8:
        return "中性"
    if hue < 15 or hue >= 345:
        return "红"
    if hue < 45:
        return "橙"
    if hue < 70:
        return "黄"
    if hue < 165:
        return "绿"
    if hue < 195:
        return "青"
    if hue < 255:
        return "蓝"
    return "紫"


def is_neutral(hue: float, sat: float, light: float) -> bool:
    """中性色判定：黑/白/灰 + 藏青 + 卡其/米。阈值是 spike 先验，待实测校准。"""
    if sat < 12:
        return True
    if light < 10 or light > 92:
        return True
    if 195 <= hue <= 245 and light <= 38 and sat <= 70:
        return True  # 藏青
    if 20 <= hue <= 60 and sat <= 50 and 55 <= light <= 88:
        return True  # 卡其 / 米
    return False


def warmth_of(hue: float, sat: float, neutral: bool) -> str:
    if neutral:
        return "neutral"
    if 165 <= hue <= 285:
        return "cool"
    if hue < 90 or hue >= 330:
        return "warm"
    return "neutral"

# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------


def norm_enum(value: str) -> str:
    v = (value or "").strip()
    if v in ENUM_SYNONYMS:
        return ENUM_SYNONYMS[v]
    return v.lower() if v.isascii() else v


def split_multi(value: str) -> tuple[str, ...]:
    raw = (value or "").replace("，", "/").replace(",", "/").replace("、", "/")
    parts = [norm_enum(p) for p in raw.split("/") if p.strip()]
    return tuple(dict.fromkeys(parts))


def parse_float(value: str) -> float | None:
    v = (value or "").strip().lower().replace("cm", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


@dataclass
class Item:
    id: int
    name: str
    category: str
    layers: tuple[str, ...]
    formality: int
    color_hex: str
    fit: str
    pattern: str
    material: str | None
    collar: str | None
    weight: str
    length_cm: float | None = None
    shoulder_cm: float | None = None
    chest_cm: float | None = None
    sleeve_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    leg_opening_cm: float | None = None
    seasons: tuple[str, ...] = ()
    notes: str = ""
    lab: tuple[float, float, float] = field(init=False)
    saturation: float = field(init=False)
    lightness: float = field(init=False)
    hue: float = field(init=False)
    hue_family: str = field(init=False)
    is_neutral: bool = field(init=False)
    warmth: str = field(init=False)

    def __post_init__(self) -> None:
        rgb = hex_to_rgb(self.color_hex)
        self.lab = rgb_to_lab(rgb)
        h, s, _ = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        self.hue = h * 360
        self.saturation = s * 100
        self.lightness = self.lab[0]
        self.hue_family = hue_family(self.hue, self.saturation, self.lightness)
        self.is_neutral = is_neutral(self.hue, self.saturation, self.lightness)
        self.warmth = warmth_of(self.hue, self.saturation, self.is_neutral)


@dataclass
class Context:
    occasion: str
    feels_like: float
    is_rainy: bool
    height_cm: float | None


@dataclass(frozen=True)
class Placement:
    slots: frozenset[str]


def placements_of(item: Item) -> list[frozenset[str]]:
    if item.category in CATEGORY_SLOTS:
        return [frozenset(CATEGORY_SLOTS[item.category])]
    out: list[frozenset[str]] = []
    for layer in item.layers:
        slot = LAYER_TO_SLOT.get(layer)
        if slot:
            p = frozenset({slot})
            if p not in out:
                out.append(p)
    return out


@dataclass
class Candidate:
    items: tuple[Item, ...]
    placement: dict[str, Item]

    @property
    def ids(self) -> tuple[int, ...]:
        return tuple(sorted({it.id for it in self.items}))

    def items_in(self, slots: tuple[str, ...]) -> list[Item]:
        seen: set[int] = set()
        out: list[Item] = []
        for slot in slots:
            it = self.placement.get(slot)
            if it and it.id not in seen:
                seen.add(it.id)
                out.append(it)
        return out

    def name(self) -> str:
        return " + ".join(it.name for it in self.items)


def enumerate_candidates(items: list[Item], anchor: Item | None = None) -> list[Candidate]:
    ordered = sorted(items, key=lambda it: (-len(placements_of(it)), it.id))
    out: list[Candidate] = []

    def suffix_slots(rest: list[Item]) -> list[frozenset[str]]:
        acc: list[frozenset[str]] = []
        union: frozenset[str] = frozenset()
        for it in reversed(rest):
            union |= frozenset().union(*placements_of(it)) if placements_of(it) else frozenset()
            acc.append(union)
        return list(reversed(acc))

    def rec(rest: list[Item], idx: int, occ: dict[str, Item], chosen: list[Item], suffix: list[frozenset[str]]) -> None:
        if idx == len(rest):
            if REQUIRED_SLOTS <= occ.keys():
                by_id = {it.id: it for it in chosen}
                out.append(Candidate(tuple(sorted(by_id.values(), key=lambda x: x.id)), dict(occ)))
            return
        if not (REQUIRED_SLOTS - occ.keys()) <= suffix[idx]:
            return

        it = rest[idx]
        # 不放
        rec(rest, idx + 1, occ, chosen, suffix)
        # 放：普通单品选一个可服务的槽位；连体装/西装套装同时占两个槽位
        for p in placements_of(it):
            if any(slot in occ for slot in p):
                continue
            new_occ = dict(occ)
            for slot in p:
                new_occ[slot] = it
            rec(rest, idx + 1, new_occ, chosen + [it], suffix)

    if anchor is None:
        rec(ordered, 0, {}, [], suffix_slots(ordered))
        return out

    if not placements_of(anchor):
        return []
    rest = [it for it in ordered if it.id != anchor.id]
    suffix = suffix_slots(rest)
    for p in placements_of(anchor):
        occ = {slot: anchor for slot in p}
        rec(rest, 0, occ, [anchor], suffix)
    return out

# ---------------------------------------------------------------------------
# 规则：24 条，返回 pass / skip / fail
# ---------------------------------------------------------------------------


@dataclass
class RuleHit:
    rule_id: str
    kind: str  # hard | soft
    status: str  # pass | fail | skip
    value: float = 0.0
    reason: str | None = None


def color_pairs(c: Candidate) -> list[tuple[Item, Item]]:
    tops = c.items_in(("base_top", "mid_layer", "outer_layer"))
    pairs = list(zip(tops, tops[1:]))
    bottom = c.placement.get("bottom")
    if tops and bottom and bottom.id != tops[-1].id:
        pairs.append((tops[-1], bottom))
    seen: set[tuple[int, int]] = set()
    out: list[tuple[Item, Item]] = []
    for a, b in pairs:
        key = tuple(sorted((a.id, b.id)))
        if key in seen:
            continue
        seen.add(key)
        out.append((a, b))
    return out


def rule_col_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    families = sorted({it.hue_family for it in main if not it.is_neutral and it.saturation >= 15})
    if len(families) <= 3:
        return RuleHit("R-COL-01", "hard", "pass")
    return RuleHit(
        "R-COL-01", "hard", "fail",
        reason=f"主色 {len(families)} 个（{'/'.join(families)}），超过 3 个",
    )


def rule_col_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bad = []
    for a, b in color_pairs(c):
        d = delta_e_hex(a.color_hex, b.color_hex)
        if d < 10 and a.hue_family != b.hue_family:
            bad.append((a, b, d))
    if not bad:
        return RuleHit("R-COL-02", "soft", "skip")
    a, b, d = bad[0]
    reason = f"{a.name} 与 {b.name} ΔE00={d:.1f} < 10，不同色系却糊在一起"
    if len(bad) > 1:
        reason += f"（共 {len(bad)} 对）"
    return RuleHit("R-COL-02", "soft", "pass", -2.0, reason)


def rule_col_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    good = []
    for a, b in color_pairs(c):
        d = delta_e_hex(a.color_hex, b.color_hex)
        if a.hue_family == b.hue_family and d >= 10:
            good.append((a, b, d))
    if not good:
        return RuleHit("R-COL-03", "soft", "skip")
    a, b, d = good[0]
    reason = f"{a.name} 与 {b.name} 同色系，ΔE00={d:.1f}，深浅有层次"
    if len(good) > 1:
        reason += f"（共 {len(good)} 对）"
    return RuleHit("R-COL-03", "soft", "pass", 2.0, reason)


def rule_col_04(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    hot = [it for it in main if it.saturation >= 60]
    cool = [it for it in hot if it.warmth == "cool"]
    warm = [it for it in hot if it.warmth == "warm"]
    if cool and warm:
        return RuleHit(
            "R-COL-04", "hard", "fail",
            reason=f"高饱和冷色（{cool[0].name}）撞高饱和暖色（{warm[0].name}）",
        )
    return RuleHit("R-COL-04", "hard", "pass")


def rule_col_05(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    total = sum(it.saturation for it in main)
    if total > 200:
        return RuleHit(
            "R-COL-05", "soft", "pass", -1.5,
            f"全身饱和度合计 {total:.0f} > 200，颜色都在抢眼",
        )
    return RuleHit("R-COL-05", "soft", "skip")


def rule_col_06(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    neutral = [it for it in main if it.is_neutral]
    if neutral:
        return RuleHit(
            "R-COL-06", "soft", "pass", 1.5,
            f"{neutral[0].name} 是中性色，能压住全身",
        )
    return RuleHit("R-COL-06", "soft", "skip")


def rule_frm_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(("base_top", "mid_layer", "outer_layer"))
    for a, b in zip(tops, tops[1:]):
        if abs(a.formality - b.formality) > 1 + tol + 1e-9:
            return RuleHit(
                "R-FRM-01", "hard", "fail",
                reason=f"{a.name}（{a.formality}）与 {b.name}（{b.formality}）正式度差 {abs(a.formality - b.formality)}",
            )
    return RuleHit("R-FRM-01", "hard", "pass")


def rule_frm_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if len(main) < 2:
        return RuleHit("R-FRM-02", "hard", "skip")
    spread = max(it.formality for it in main) - min(it.formality for it in main)
    if spread > 2 + tol + 1e-9:
        return RuleHit("R-FRM-02", "hard", "fail", reason=f"全身正式度极差 {spread} > 2")
    return RuleHit("R-FRM-02", "hard", "pass")


def _upper(c: Candidate) -> Item | None:
    return c.placement.get("outer_layer") or c.placement.get("base_top")


def rule_prp_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if not upper or not lower:
        return RuleHit("R-PRP-01", "hard", "skip")
    if upper.fit == "oversize" and lower.fit == "oversize":
        return RuleHit("R-PRP-01", "hard", "fail", reason="上宽下也宽，整体会垮")
    return RuleHit("R-PRP-01", "hard", "pass")


def rule_prp_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if not upper or not lower:
        return RuleHit("R-PRP-02", "hard", "skip")
    if upper.fit == "slim" and lower.fit == "slim":
        return RuleHit("R-PRP-02", "hard", "fail", reason="上紧下也紧，看着局促")
    return RuleHit("R-PRP-02", "hard", "pass")


def rule_prp_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if not upper or not lower:
        return RuleHit("R-PRP-03", "soft", "skip")
    diff = FIT_IDX[upper.fit] - FIT_IDX[lower.fit]
    # 02 的原文是“上宽下窄 / 上窄下宽”：宽=oversize，窄=slim。
    # regular 与 slim 只差一级，不算宽窄对比，所以要求跨两级。
    if abs(diff) >= 2:
        return RuleHit(
            "R-PRP-03", "soft", "pass", 2.0,
            f"上装{FIT_CN[upper.fit]}、下装{FIT_CN[lower.fit]}，有宽窄对比",
        )
    return RuleHit("R-PRP-03", "soft", "skip")


def rule_prp_04(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if ctx.height_cm is None or ctx.height_cm >= 170:
        return RuleHit("R-PRP-04", "soft", "skip")
    outer = c.placement.get("outer_layer")
    if not outer or outer.length_cm is None:
        return RuleHit("R-PRP-04", "soft", "skip")
    threshold = 0.55 * ctx.height_cm
    if outer.length_cm >= threshold:
        return RuleHit(
            "R-PRP-04", "soft", "pass", -1.0,
            f"身高 {ctx.height_cm:.0f}cm，{outer.name} 长 {outer.length_cm:.0f}cm，下摆压身高",
        )
    return RuleHit("R-PRP-04", "soft", "skip")


def rule_lyr_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(("base_top", "mid_layer", "outer_layer"))
    if len(tops) < 2:
        return RuleHit("R-LYR-01", "hard", "skip")
    if any(it.weight not in WEIGHT_IDX for it in tops):
        return RuleHit("R-LYR-01", "hard", "skip")
    # 02 §4.4：允许同厚，档位 1/2 不再额外放宽；只有档位 3（tol=2.0）
    # 允许外层比相邻内层薄一级。
    required = -1 if tol >= 1.5 else 0
    for a, b in zip(tops, tops[1:]):
        if WEIGHT_IDX[b.weight] - WEIGHT_IDX[a.weight] < required:
            return RuleHit(
                "R-LYR-01", "hard", "fail",
                reason=f"{b.name}（{b.weight}）比 {a.name}（{a.weight}）薄，厚度倒挂",
            )
    return RuleHit("R-LYR-01", "hard", "pass")


def rule_lyr_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    base = c.placement.get("base_top")
    mid = c.placement.get("mid_layer")
    outer = c.placement.get("outer_layer")
    if not (base and mid and outer):
        return RuleHit("R-LYR-02", "soft", "skip")
    lengths = [base.length_cm, mid.length_cm, outer.length_cm]
    if any(v is None for v in lengths):
        return RuleHit("R-LYR-02", "soft", "skip")
    diffs = [abs(lengths[0] - lengths[1]), abs(lengths[1] - lengths[2])]  # type: ignore[operator]
    if all(d >= 5 for d in diffs):
        return RuleHit(
            "R-LYR-02", "soft", "pass", 1.5,
            f"三层长度差 {diffs[0]:.0f}cm / {diffs[1]:.0f}cm，层次拉得开",
        )
    return RuleHit("R-LYR-02", "soft", "skip")


def rule_lyr_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(("base_top", "mid_layer", "outer_layer"))
    # “两层领型重复”指任意两层，不限于相邻层：高领内搭 + V 领中层 + 高领外套
    # 仍然是双高领。所以检查所有两两组合。
    for i, a in enumerate(tops):
        for b in tops[i + 1:]:
            if a.collar and b.collar and a.collar == b.collar and a.collar in {"高领", "连帽"}:
                return RuleHit(
                    "R-LYR-03", "soft", "pass", -1.5,
                    f"{a.name} 与 {b.name} 都是{a.collar}，领口重复",
                )
    return RuleHit("R-LYR-03", "soft", "skip")


def rule_mat_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    # “相邻层材质对比”：逐对检查 base→mid、mid→outer，任意一对成立即可，
    # 而不是只看最外层与最内层。
    tops = c.items_in(("base_top", "mid_layer", "outer_layer"))
    for inner, outer in zip(tops, tops[1:]):
        if inner.id == outer.id or not inner.material or not outer.material:
            continue
        if outer.material in STIFF_MATERIALS and inner.material in SOFT_MATERIALS:
            return RuleHit(
                "R-MAT-01", "soft", "pass", 1.5,
                f"外层{outer.material}挺括、内层{inner.material}柔软，有材质对比",
            )
    return RuleHit("R-MAT-01", "soft", "skip")


def rule_pat_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    # 02 写的是“全身 pattern=bold 最多一件”，配饰也算全身的一部分。
    bold = [it for it in c.items if it.pattern == "bold"]
    if len(bold) > 1:
        return RuleHit(
            "R-PAT-01", "hard", "fail",
            reason=f"大图案有 {len(bold)} 件（{'、'.join(it.name for it in bold)}），超过 1 件",
        )
    return RuleHit("R-PAT-01", "hard", "pass")


def rule_pat_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bold = [it for it in c.items if it.pattern == "bold"]
    if len(bold) != 1:
        return RuleHit("R-PAT-02", "soft", "skip")
    b = bold[0]
    in_visual = any(c.placement.get(slot) is b for slot in ("outer_layer", "bottom"))
    others = [it for it in c.items if it.id != b.id]
    if in_visual and all(it.pattern == "solid" for it in others):
        return RuleHit(
            "R-PAT-02", "soft", "pass", 1.0,
            f"图案在{b.name}上，其余纯色，视觉有主次",
        )
    return RuleHit("R-PAT-02", "soft", "skip")


def rule_sho_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    shoe = c.placement.get("shoes")
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if not shoe or not main:
        return RuleHit("R-SHO-01", "hard", "skip")
    mean = sum(it.formality for it in main) / len(main)
    diff = abs(shoe.formality - mean)
    if diff > 1 + tol + 1e-9:
        return RuleHit(
            "R-SHO-01", "hard", "fail",
            reason=f"{shoe.name} 正式度 {shoe.formality}，全身均值 {mean:.1f}，差 {diff:.1f} > 1",
        )
    return RuleHit("R-SHO-01", "hard", "pass")


def rule_sho_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    shoe = c.placement.get("shoes")
    if not shoe:
        return RuleHit("R-SHO-02", "soft", "skip")
    targets = c.items_in(("base_top", "mid_layer", "outer_layer", "accessory"))
    for it in targets:
        if it.id == shoe.id:
            continue
        if it.hue_family == shoe.hue_family and delta_e_hex(it.color_hex, shoe.color_hex) < 25:
            return RuleHit(
                "R-SHO-02", "soft", "pass", 1.5,
                f"{shoe.name} 与 {it.name} 同色系，整套有呼应",
            )
    return RuleHit("R-SHO-02", "soft", "skip")


def rule_sho_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if not ctx.is_rainy:
        return RuleHit("R-SHO-03", "soft", "skip")
    shoe = c.placement.get("shoes")
    if not shoe or not shoe.material:
        return RuleHit("R-SHO-03", "soft", "skip")
    if shoe.material in RAIN_BAD:
        return RuleHit(
            "R-SHO-03", "soft", "pass", -1.5,
            f"降水天穿 {shoe.name}（{shoe.material}），容易湿",
        )
    if shoe.material in RAIN_GOOD:
        return RuleHit(
            "R-SHO-03", "soft", "pass", 1.0,
            f"降水天穿 {shoe.name}（{shoe.material}），能应付",
        )
    return RuleHit("R-SHO-03", "soft", "skip")


def _band_ok(t: float, c: Candidate) -> bool:
    base = c.placement.get("base_top")
    mid = c.placement.get("mid_layer")
    outer = c.placement.get("outer_layer")
    if not base or base.weight not in WEIGHT_IDX:
        return True
    if t >= 26:
        return mid is None and outer is None and base.weight == "thin"
    if t >= 18:
        return (
            mid is None
            and (outer is None or outer.weight == "thin")
            and base.weight in {"thin", "medium"}
        )
    if t >= 10:
        return (mid is not None or outer is not None) and all(
            it.weight in {"thin", "medium"} for it in (base, mid, outer) if it
        )
    # <10°C：三层，中层与外层 medium/thick。内层允许 thin/medium/thick——
    # 02 的表格只说“可穿厚度 medium/thick”，没有禁止厚内搭；
    # 厚毛衣当内层在冬天是正常穿法。这里按“中层/外层必须够厚”判。
    return (
        mid is not None
        and outer is not None
        and mid.weight in {"medium", "thick"}
        and outer.weight in {"medium", "thick"}
    )


def _band_label(t: float) -> str:
    if t >= 26:
        return "≥26°C 只内层"
    if t >= 18:
        return "18–26°C 单层或薄外套"
    if t >= 10:
        return "10–18°C 需中层或外套"
    return "<10°C 三层"


def rule_occ_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    temps = {ctx.feels_like}
    if tol:
        temps |= {ctx.feels_like - tol, ctx.feels_like + tol}
    for boundary in (10.0, 18.0, 26.0):
        if ctx.feels_like - tol <= boundary <= ctx.feels_like + tol:
            temps.add(boundary)
    if any(_band_ok(t, c) for t in temps):
        return RuleHit("R-OCC-01", "hard", "pass")
    base = c.placement.get("base_top")
    mid = c.placement.get("mid_layer")
    outer = c.placement.get("outer_layer")
    desc = " / ".join(
        f"{label} {it.weight}" for label, it in (("内", base), ("中", mid), ("外", outer)) if it
    )
    return RuleHit(
        "R-OCC-01", "hard", "fail",
        reason=f"体感 {ctx.feels_like:.1f}°C（{_band_label(ctx.feels_like)}），当前 {desc} 不兼容",
    )


def rule_occ_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    if not main:
        return RuleHit("R-OCC-02", "soft", "skip")
    mean = sum(it.formality for it in main) / len(main)
    if ctx.occasion in {"日常", "旅游"}:
        lo, hi = 2.0, 3.0
    elif ctx.occasion == "见人":
        lo, hi = 3.5, 4.5
    else:
        return RuleHit("R-OCC-02", "soft", "skip")
    if lo <= mean <= hi:
        return RuleHit(
            "R-OCC-02", "soft", "pass", 2.0,
            f"场合「{ctx.occasion}」，正式度均值 {mean:.1f}，落在 {lo:g}–{hi:g}",
        )
    return RuleHit("R-OCC-02", "soft", "skip")


def rule_occ_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if not main or any(it.weight not in WARMTH for it in main):
        return RuleHit("R-OCC-03", "soft", "skip")
    mean = sum(WARMTH[it.weight] for it in main) / len(main)
    target = max(1.0, min(5.5, 1 + (30 - ctx.feels_like) / 7))
    dev = abs(mean - target)
    if dev <= 0.5:
        return RuleHit(
            "R-OCC-03", "soft", "pass", 1.5,
            f"体感 {ctx.feels_like:.1f}°C，暖度目标 {target:.1f}，这套 {mean:.1f}，匹配",
        )
    return RuleHit("R-OCC-03", "soft", "skip")


HARD_RULES = [
    ("R-COL-01", rule_col_01, False),
    ("R-COL-04", rule_col_04, False),
    ("R-FRM-01", rule_frm_01, True),
    ("R-FRM-02", rule_frm_02, True),
    ("R-PRP-01", rule_prp_01, False),
    ("R-PRP-02", rule_prp_02, False),
    ("R-LYR-01", rule_lyr_01, True),
    ("R-PAT-01", rule_pat_01, False),
    ("R-SHO-01", rule_sho_01, True),
    ("R-OCC-01", rule_occ_01, True),
]
RELAXABLE = {rid for rid, _, relaxable in HARD_RULES if relaxable}

SOFT_RULES = [
    ("R-COL-02", rule_col_02),
    ("R-COL-03", rule_col_03),
    ("R-COL-05", rule_col_05),
    ("R-COL-06", rule_col_06),
    ("R-PRP-03", rule_prp_03),
    ("R-PRP-04", rule_prp_04),
    ("R-LYR-02", rule_lyr_02),
    ("R-LYR-03", rule_lyr_03),
    ("R-MAT-01", rule_mat_01),
    ("R-PAT-02", rule_pat_02),
    ("R-SHO-02", rule_sho_02),
    ("R-SHO-03", rule_sho_03),
    ("R-OCC-02", rule_occ_02),
    ("R-OCC-03", rule_occ_03),
]

assert len(HARD_RULES) + len(SOFT_RULES) == 24, "规则总数必须是 24"


def evaluate_hard(c: Candidate, ctx: Context, tol: float) -> dict[str, RuleHit]:
    out: dict[str, RuleHit] = {}
    for rid, fn, relaxable in HARD_RULES:
        out[rid] = fn(c, ctx, tol if relaxable else 0.0)
    return out


def evaluate_soft(c: Candidate, ctx: Context) -> list[RuleHit]:
    return [fn(c, ctx, 0.0) for _, fn in SOFT_RULES]


PENALTY = {0: 0.0, 1: 1.0, 2: 2.0, 3: 4.0}


@dataclass
class Assessment:
    candidate: Candidate
    level: int
    relaxed_rules: list[str]
    score: float
    soft_hits: list[RuleHit]
    reason: str

    @property
    def thumbs_up(self) -> list[str]:
        return [h.rule_id for h in self.soft_hits if h.value > 0]

    @property
    def thumbs_down(self) -> list[str]:
        return [h.rule_id for h in self.soft_hits if h.value < 0]


def assess(c: Candidate, ctx: Context) -> Assessment | None:
    strict = evaluate_hard(c, ctx, 0.0)
    for level, tol in enumerate((0.0, 0.5, 1.0, 2.0)):
        hard = strict if level == 0 else evaluate_hard(c, ctx, tol)
        if any(h.status == "fail" for h in hard.values()):
            continue
        relaxed_ids = [
            rid for rid, h in hard.items()
            if strict[rid].status == "fail" and h.status != "fail" and rid in RELAXABLE
        ]
        soft = evaluate_soft(c, ctx)
        score = sum(h.value for h in soft if h.status == "pass") - len(relaxed_ids) * PENALTY[level]
        reasons = [h.reason for h in soft if h.reason and h.value != 0]
        reason = "；".join(reasons[:4]) if reasons else "硬规则全部通过，软规则无命中"
        if relaxed_ids:
            # 放宽必须说清楚“放宽了哪条、原来为什么不过”，否则界面上只剩一个
            # “放宽 2 档”的标签，用户无法判断这套到底哪里让步了。
            details = []
            for rid in relaxed_ids:
                strict_reason = strict[rid].reason or "未记录原因"
                details.append(f"{rid}：{strict_reason}")
            reason = f"放宽 {level} 档（{'；'.join(details)}）：" + reason
        return Assessment(c, level, relaxed_ids, round(score, 2), soft, reason)
    return None


def dedup(assessments: list[Assessment], n: int = 10) -> list[Assessment]:
    selected: list[Assessment] = []
    for a in assessments:
        ids = set(a.candidate.ids)
        if any(len(ids & set(s.candidate.ids)) >= 3 for s in selected):
            continue
        selected.append(a)
        if len(selected) >= n:
            break
    return selected

# ---------------------------------------------------------------------------
# 读数据
# ---------------------------------------------------------------------------


def load_rows(path: Path) -> list[dict[str, str]]:
    """读 CSV 或 xlsx，统一成「列名 → 字符串」的行列表。"""
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "读 xlsx 需要 openpyxl；也可以用 Excel 导出 CSV 后再跑"
            ) from exc
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb["填写"] if "填写" in wb.sheetnames else wb[wb.sheetnames[0]]
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            raise SystemExit(f"空文件：{path}")
        header = [str(h).strip() if h is not None else "" for h in header]
        if "名称" not in header:
            raise SystemExit(f"表头缺「名称」列：{path}")
        return [
            {h: "" if v is None else str(v).strip() for h, v in zip(header, raw)}
            for raw in rows
        ]

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"空文件：{path}")
        return [
            {k: "" if v is None else str(v).strip() for k, v in row.items()}
            for row in reader
        ]


def read_items(path: Path) -> tuple[list[Item], list[str]]:
    warnings: list[str] = []
    items: list[Item] = []
    seen_ids: set[int] = set()
    for row_no, row in enumerate(load_rows(path), start=2):
        name = row.get("名称") or ""
        if not name or name.startswith("示例"):
            continue
        category = row.get("品类") or ""
        if category not in KNOWN_CATEGORIES:
            warnings.append(f"第 {row_no} 行「{name}」品类未知（{category!r}），已跳过")
            continue
        layers = split_multi(row.get("层级") or "")
        if category not in CATEGORY_SLOTS and not layers:
            warnings.append(
                f"第 {row_no} 行「{name}」层级为空，放不进任何槽位，已跳过"
            )
            continue
        try:
            formality = int(float(row.get("正式度") or ""))
        except ValueError:
            warnings.append(f"第 {row_no} 行「{name}」正式度不是 1–5，已跳过")
            continue
        if not 1 <= formality <= 5:
            warnings.append(f"第 {row_no} 行「{name}」正式度 {formality} 超出 1–5，已跳过")
            continue
        fit = norm_enum(row.get("版型") or "")
        pattern = norm_enum(row.get("图案") or "")
        weight = norm_enum(row.get("厚度") or "")
        if fit not in FIT_IDX or pattern not in {"solid", "fine", "bold"} or weight not in WEIGHT_IDX:
            warnings.append(
                f"第 {row_no} 行「{name}」版型/图案/厚度不完整（{fit}/{pattern}/{weight}），已跳过"
            )
            continue
        try:
            hex_to_rgb(row.get("颜色HEX") or "")
        except ValueError:
            warnings.append(f"第 {row_no} 行「{name}」颜色 HEX 无效，已跳过")
            continue

        raw_id = row.get("编号") or ""
        try:
            item_id = int(float(raw_id)) if raw_id else row_no
        except ValueError:
            item_id = row_no
        if item_id in seen_ids:
            warnings.append(f"第 {row_no} 行「{name}」编号 {item_id} 重复，改为 {row_no}")
            item_id = row_no
        seen_ids.add(item_id)

        is_bottom = category in BOTTOM_CATEGORIES
        length = parse_float(row.get("裤长cm") if is_bottom else row.get("衣长cm"))
        if is_bottom and length is None:
            length = parse_float(row.get("衣长cm"))
        material = norm_enum(row.get("材质") or "") or None
        collar = norm_enum(row.get("领型") or "") or None

        items.append(
            Item(
                id=item_id,
                name=name,
                category=category,
                layers=layers,
                formality=formality,
                color_hex=row.get("颜色HEX") or "",
                fit=fit,
                pattern=pattern,
                material=material,
                collar=collar,
                weight=weight,
                length_cm=length,
                shoulder_cm=parse_float(row.get("肩宽cm")),
                chest_cm=parse_float(row.get("胸宽cm")),
                sleeve_cm=parse_float(row.get("袖长cm")),
                waist_cm=parse_float(row.get("平铺腰围cm")),
                hip_cm=parse_float(row.get("平铺臀围cm")),
                leg_opening_cm=parse_float(row.get("脚口宽cm")),
                seasons=split_multi(row.get("季节") or ""),
                notes=row.get("备注") or "",
            )
        )

    if not items:
        detail = "\n".join(warnings)
        raise SystemExit(f"没有读到任何有效单品：{path}" + (f"\n{detail}" if detail else ""))
    return items, warnings


def item_to_dict(it: Item) -> dict:
    return {
        "id": it.id,
        "name": it.name,
        "category": it.category,
        "layers": list(it.layers),
        "formality": it.formality,
        "color_hex": it.color_hex,
        "hue_family": it.hue_family,
        "saturation": round(it.saturation, 1),
        "lightness": round(it.lightness, 1),
        "is_neutral": it.is_neutral,
        "fit": it.fit,
        "pattern": it.pattern,
        "material": it.material,
        "collar": it.collar,
        "weight": it.weight,
        "length_cm": it.length_cm,
        "shoulder_cm": it.shoulder_cm,
        "chest_cm": it.chest_cm,
        "sleeve_cm": it.sleeve_cm,
        "waist_cm": it.waist_cm,
        "hip_cm": it.hip_cm,
        "leg_opening_cm": it.leg_opening_cm,
    }


def assessment_to_dict(a: Assessment) -> dict:
    return {
        "garments": [
            {"id": it.id, "name": it.name, "category": it.category}
            for it in a.candidate.items
        ],
        "garment_ids": list(a.candidate.ids),
        "score": a.score,
        "relaxed": a.level,
        "relaxed_rules": a.relaxed_rules,
        "thumbs_up": a.thumbs_up,
        "thumbs_down": a.thumbs_down,
        "reason": a.reason,
    }

# ---------------------------------------------------------------------------
# 统计与输出
# ---------------------------------------------------------------------------


def rule_health(candidates: list[Candidate], ctx: Context) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {
        rid: {"pass": 0, "fail": 0, "skip": 0, "value": 0.0} for rid in RULE_NAMES
    }
    for c in candidates:
        for h in list(evaluate_hard(c, ctx, 0.0).values()) + evaluate_soft(c, ctx):
            stats[h.rule_id][h.status] += 1
            stats[h.rule_id]["value"] += h.value
    return stats


def print_rule_health(stats: dict[str, dict[str, float]], total: int) -> bool:
    """硬规则看 fail%，软规则看命中率与平均分。

    两类规则的 pass 语义不同：硬规则 pass = 合规；软规则 pass = 命中（可能加分
    也可能扣分）。混在一张表里会让「软规则 fail 0」看起来像没生效。
    """
    print(f"\n硬规则（strict 档，{total} 个槽位合法候选）")
    print(f"{'规则':<10} {'名称':<24} {'pass':>6} {'fail':>6} {'skip':>6} {'fail%':>7}")
    all_ok = True
    for rid, _, _ in HARD_RULES:
        s = stats[rid]
        fail_rate = s["fail"] / total * 100 if total else 0
        flag = ""
        if fail_rate >= 99.999:
            flag = "  ← 100% fail"
            all_ok = False
        print(
            f"{rid:<10} {RULE_NAMES[rid]:<24} {int(s['pass']):>6} {int(s['fail']):>6} "
            f"{int(s['skip']):>6} {fail_rate:>6.1f}%{flag}"
        )

    print(f"\n软规则（命中 = 该条给出加分或扣分；skip = 数据不足，不参与）")
    print(f"{'规则':<10} {'名称':<24} {'命中':>6} {'跳过':>6} {'命中%':>7} {'平均分':>7}")
    for rid, _ in SOFT_RULES:
        s = stats[rid]
        hit_rate = s["pass"] / total * 100 if total else 0
        mean_value = s["value"] / s["pass"] if s["pass"] else 0.0
        print(
            f"{rid:<10} {RULE_NAMES[rid]:<24} {int(s['pass']):>6} {int(s['skip']):>6} "
            f"{hit_rate:>6.1f}% {mean_value:>+7.2f}"
        )
    return all_ok


def rank_key(a: Assessment) -> tuple:
    """严格档永远排在放宽档前面；同档内按得分从高到低。"""
    return (a.level, -a.score, len(a.candidate.items), a.candidate.ids)


def cumulative(assessments: list[Assessment], max_level: int, n: int = 10) -> list[Assessment]:
    pool = [a for a in assessments if a.level <= max_level]
    return dedup(sorted(pool, key=rank_key), n=n)


def newly_admitted(assessments: list[Assessment], level: int, n: int = 10) -> list[Assessment]:
    pool = [a for a in assessments if a.level == level]
    return dedup(sorted(pool, key=rank_key), n=n)


def exclusion_reason(item: Item, candidates: list[Candidate], ctx: Context) -> str:
    """解释一件单品为什么在当前上下文下配不出结果，供锚定池排除项使用。"""
    containing = [c for c in candidates if item.id in c.ids]
    if not containing:
        return "没有可落的槽位（检查「层级」与「品类」）"
    fails: dict[str, int] = {}
    for c in containing:
        for rid, h in evaluate_hard(c, ctx, 0.0).items():
            if h.status == "fail":
                fails[rid] = fails.get(rid, 0) + 1
    if not fails:
        return "硬规则通过但未进入结果（检查去重与评分）"
    rid, count = max(fails.items(), key=lambda kv: kv[1])
    return f"{len(containing)} 套含此件的候选全被硬规则拦下，主因 {rid}（{count} 次）"


def main() -> None:
    parser = argparse.ArgumentParser(description="M1 开工前干跑：24 条规则 + 槽位枚举 + 放宽 + 去重 + 锚定")
    parser.add_argument("--items", type=Path, required=True, help="items CSV 路径")
    parser.add_argument("--occasion", default="日常", choices=["日常", "旅游", "见人"])
    parser.add_argument("--feels-like", type=float, default=15.0, help="体感温度 °C")
    parser.add_argument("--rain", action="store_true", help="是否降水")
    parser.add_argument("--height", type=float, default=175.0, help="身高 cm，用于 R-PRP-04")
    parser.add_argument("--anchors", type=int, default=5, help="锚定测试件数")
    parser.add_argument("--out", type=Path, default=None, help="JSON 输出路径")
    args = parser.parse_args()

    t0 = time.perf_counter()
    items, warnings = read_items(args.items)
    ctx = Context(args.occasion, args.feels_like, args.rain, args.height)

    for w in warnings:
        print(f"⚠️  {w}")

    candidates = enumerate_candidates(items)
    t_enum = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    assessments = [a for c in candidates if (a := assess(c, ctx)) is not None]
    t_assess = (time.perf_counter() - t1) * 1000

    stats = rule_health(candidates, ctx)

    print("=" * 78)
    print("M1 干跑报告")
    print("=" * 78)
    print(f"输入：{args.items}")
    print(f"单品 {len(items)} 件 | 上下文：{ctx.occasion} / 体感 {ctx.feels_like:.1f}°C / "
          f"{'降水' if ctx.is_rainy else '无降水'} / 身高 {ctx.height_cm:.0f}cm")
    print(f"槽位合法候选 {len(candidates)} 套 | 枚举 {t_enum:.0f}ms + 规则评估 {t_assess:.0f}ms")

    health_ok = print_rule_health(stats, len(candidates))

    print("\n各档结果（新增 = 本档才被放宽接纳；累计 = 放宽到该档时可见的全部组合）")
    print(f"{'档位':<6} {'新增候选':>8} {'累计候选':>8} {'新增去重':>8} {'累计去重':>8}")
    level_counts = {}
    for level in range(4):
        new = sum(1 for a in assessments if a.level == level)
        pool = [a for a in assessments if a.level <= level]
        new_deduped = newly_admitted(assessments, level)
        deduped = cumulative(assessments, level)
        level_counts[level] = {
            "new_candidates": new,
            "new_deduped": len(new_deduped),
            "cumulative_candidates": len(pool),
            "cumulative_deduped": len(deduped),
        }
        print(
            f"{level:<6} {new:>8} {len(pool):>8} "
            f"{len(new_deduped):>8} {len(deduped):>8}"
        )

    for level in range(4):
        top = newly_admitted(assessments, level, n=10)
        print(f"\n放宽 {level} 档 · 新增前 {len(top)} 套（去重后）")
        if not top:
            print("  （无）")
            continue
        for rank, a in enumerate(top, start=1):
            mark = f"  [放宽 {a.level}]" if a.level else ""
            print(f"  {rank}. {a.candidate.name()}  | 得分 {a.score:.1f}{mark}")
            print(f"     {a.reason}")

    # 锚定
    t2 = time.perf_counter()
    # 只在「至少能进一套结果」的单品里抽样。否则锚定测试测的是温度门槛，
    # 不是求解器；被排除的单品单独列出并说明原因。
    solvable_ids = {it.id for a in assessments for it in a.candidate.items}
    anchor_pool = [it for it in items if it.id in solvable_ids]
    excluded = [it for it in items if it.id not in solvable_ids]
    rng = random.Random(42)
    chosen = rng.sample(anchor_pool, min(args.anchors, len(anchor_pool)))
    anchor_results = []
    print(f"\n锚定测试（随机种子 42，可锚定池 {len(anchor_pool)} 件）")
    print(f"{'锚点':<22} {'L0':>4} {'L1':>4} {'L2':>4} {'L3':>4}  判定")
    for anchor in chosen:
        ac = enumerate_candidates(items, anchor)
        aa = [a for c in ac if (a := assess(c, ctx)) is not None]
        counts = [len(cumulative(aa, level)) for level in range(4)]
        best = next((level for level, n in enumerate(counts) if n >= 3), None)
        ok = best is not None
        anchor_results.append({
            "anchor": {"id": anchor.id, "name": anchor.name, "category": anchor.category},
            "counts": counts,
            "best_level": best,
            "ok": ok,
        })
        print(
            f"#{anchor.id} {anchor.name:<18} {counts[0]:>4} {counts[1]:>4} "
            f"{counts[2]:>4} {counts[3]:>4}  {'✅' if ok else '❌'}"
        )
    if excluded:
        print("\n未进锚定池（当前上下文下 0 套结果）")
        for it in excluded:
            print(f"  #{it.id} {it.name}：{exclusion_reason(it, candidates, ctx)}")
    t_anchor = (time.perf_counter() - t2) * 1000

    # 验收
    strict_ok = level_counts[0]["cumulative_deduped"] >= 1
    relax_ok = level_counts[3]["cumulative_deduped"] >= 10
    anchor_ok = all(r["ok"] for r in anchor_results)
    perf_ok = (t_enum + t_assess) < 200
    checks = {
        "strict_ge_1": strict_ok,
        "relaxed3_dedup_ge_10": relax_ok,
        "anchors_ge_3": anchor_ok,
        "no_rule_100pct_fail": health_ok,
        "under_200ms": perf_ok,
    }
    print("\n验收（07 第 2 节）")
    print(f"  [{'✅' if strict_ok else '❌'}] 严格档 ≥1 套（实际 {level_counts[0]['cumulative_deduped']}）")
    print(f"  [{'✅' if relax_ok else '❌'}] 放宽到第 3 档去重 ≥10 套（实际 {level_counts[3]['cumulative_deduped']}）")
    print(f"  [{'✅' if anchor_ok else '❌'}] 随机锚点每件 ≥3 套")
    print(f"  [{'✅' if health_ok else '❌'}] 没有硬规则 100% fail")
    print(f"  [{'✅' if perf_ok else '❌'}] 求解 <200ms（实际 {t_enum + t_assess:.0f}ms）")
    if not all(checks.values()):
        print("  → 失败项按 07 第 2 节「失败时改哪」处理，先改文档再改代码。")

    # JSON
    out_path = args.out or (Path(__file__).resolve().parent / "dryrun_result.json")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.items),
        "context": {
            "occasion": ctx.occasion,
            "feels_like": ctx.feels_like,
            "is_rainy": ctx.is_rainy,
            "height_cm": ctx.height_cm,
        },
        "items": [item_to_dict(it) for it in items],
        "candidate_count": len(candidates),
        "level_counts": level_counts,
        "rule_stats": stats,
        "levels": {
            str(level): {
                "new": [assessment_to_dict(a) for a in newly_admitted(assessments, level)],
                "cumulative": [assessment_to_dict(a) for a in cumulative(assessments, level)],
            }
            for level in range(4)
        },
        "anchors": anchor_results,
        "anchor_pool_ids": [it.id for it in anchor_pool],
        "anchor_excluded": [
            {"id": it.id, "name": it.name, "reason": exclusion_reason(it, candidates, ctx)}
            for it in excluded
        ],
        "timing_ms": {
            "enumerate": round(t_enum, 1),
            "assess": round(t_assess, 1),
            "anchor": round(t_anchor, 1),
        },
        "checks": checks,
        "warnings": warnings,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整结果：{out_path}")


if __name__ == "__main__":
    main()
