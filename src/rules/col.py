"""色彩模块（COL）——6 条规则。

课程口径：一套衣服"好看"的第一步不是好看，是**不打架**。
颜色只有两种坏：糊成一片（太近）、互相抢（太多、太艳、冷暖相撞）。
中性色是安全垫，深浅同色系是廉价的高级感。

- R-COL-01 硬：全身主色 ≤ 3 个（主色 = 有彩度且非中性色，按色系去重）
- R-COL-02 软：相邻层 ΔE00 < 10 且不同色系 → 糊成一片，−2
- R-COL-03 软：同色系且 ΔE00 ≥ 10 → 深浅叠穿，+2
- R-COL-04 硬：高饱和冷色与高饱和暖色同时出现 → 抢眼相撞
- R-COL-05 软：全身饱和度合计 > 200 → 都在抢眼，−1.5
- R-COL-06 软：至少一件中性色打底，+1.5
"""

from __future__ import annotations

from .color_math import delta_e_hex
from .types import Candidate, Context, Item, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

# 参与"全身"判定的槽位（配饰不计入主色与饱和度总量）
BODY_SLOTS = ("base_top", "mid_layer", "outer_layer", "bottom", "shoes")
TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")

MAX_MAIN_COLORS = 3
BLUR_DELTA_E = 10.0
SAT_SUM_MAX = 200.0


def color_pairs(candidate: Candidate) -> list[tuple[Item, Item]]:
    """需要检查色差的相邻对：内→中→外，加最外层（或内层）与下装。"""
    tops = candidate.items_in(TOP_SLOTS)
    pairs = list(zip(tops, tops[1:]))
    bottom = candidate.placement.get("bottom")
    if tops and bottom is not None and bottom.id != tops[-1].id:
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
    families = sorted(
        {it.hue_family for it in c.items_in(BODY_SLOTS) if it.colors.is_main_color}
    )
    if len(families) <= MAX_MAIN_COLORS:
        return RuleHit("R-COL-01", HARD, PASS)
    return RuleHit(
        "R-COL-01", HARD, FAIL,
        reason=f"主色 {len(families)} 个（{'/'.join(families)}），超过 3 个",
    )


def rule_col_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bad = [
        (a, b, d)
        for a, b in color_pairs(c)
        if (d := delta_e_hex(a.color_hex, b.color_hex)) < BLUR_DELTA_E
        and a.hue_family != b.hue_family
    ]
    if not bad:
        return RuleHit("R-COL-02", SOFT, SKIP)
    a, b, d = bad[0]
    reason = f"{a.name}与{b.name} ΔE00={d:.1f} < 10，不同色系却糊在一起"
    if len(bad) > 1:
        reason += f"（共 {len(bad)} 对）"
    return RuleHit("R-COL-02", SOFT, PASS, -2.0, reason)


def rule_col_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    good = [
        (a, b, d)
        for a, b in color_pairs(c)
        if a.hue_family == b.hue_family
        and (d := delta_e_hex(a.color_hex, b.color_hex)) >= BLUR_DELTA_E
    ]
    if not good:
        return RuleHit("R-COL-03", SOFT, SKIP)
    a, b, d = good[0]
    reason = f"{a.name}与{b.name}同色系，ΔE00={d:.1f}，深浅有层次"
    if len(good) > 1:
        reason += f"（共 {len(good)} 对）"
    return RuleHit("R-COL-03", SOFT, PASS, 2.0, reason)


def rule_col_04(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    hot = [it for it in c.items_in(BODY_SLOTS) if it.colors.is_high_sat]
    cool = [it for it in hot if it.warmth == "cool"]
    warm = [it for it in hot if it.warmth == "warm"]
    if cool and warm:
        return RuleHit(
            "R-COL-04", HARD, FAIL,
            reason=f"高饱和冷色（{cool[0].name}）撞高饱和暖色（{warm[0].name}）",
        )
    return RuleHit("R-COL-04", HARD, PASS)


def rule_col_05(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    total = sum(it.saturation for it in c.items_in(BODY_SLOTS))
    if total > SAT_SUM_MAX:
        return RuleHit(
            "R-COL-05", SOFT, PASS, -1.5,
            f"全身饱和度合计 {total:.0f} > 200，颜色都在抢眼",
        )
    return RuleHit("R-COL-05", SOFT, SKIP)


def rule_col_06(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    neutral = [it for it in c.items_in(BODY_SLOTS) if it.is_neutral]
    if neutral:
        return RuleHit(
            "R-COL-06", SOFT, PASS, 1.5, f"{neutral[0].name}是中性色，能压住全身"
        )
    return RuleHit("R-COL-06", SOFT, SKIP)


RULES = (
    ("R-COL-01", rule_col_01),
    ("R-COL-02", rule_col_02),
    ("R-COL-03", rule_col_03),
    ("R-COL-04", rule_col_04),
    ("R-COL-05", rule_col_05),
    ("R-COL-06", rule_col_06),
)

__all__ = ["RULES", "color_pairs"]
