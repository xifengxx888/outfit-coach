"""场合与温度模块（OCC）——3 条规则。

课程口径：**穿多少由体感温度决定，不由季节名字决定**。
同样 12°C，有风与无风是两种穿法；10 月底在深圳和哈尔滨也不是一个季节。
正式度档位只做硬约束（防止 26°C 穿厚外套），连续目标做软评分
（防止 25.9°C 与 26.1°C 之间出现断层）。

- R-OCC-01 硬：上装三层厚度与体感温度区间兼容（下装与鞋不参与）
- R-OCC-02 软：场合 → 目标正式度区间，命中 +2
- R-OCC-03 软：组合暖度接近 `target_warmth(t)`，+1.5

体感温度缺失时，01 与 03 返回 SKIP：没数据不等于穿错。
"""

from __future__ import annotations

from .types import WARMTH, Candidate, Context, Item, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")
BAND_BOUNDARIES = (10.0, 18.0, 26.0)

# 场合 → 正式度区间（02 第五节）
OCCASION_FORMALITY = {
    "日常": (2.0, 3.0),
    "旅游": (2.0, 3.0),
    "见人": (3.5, 4.5),
}
OCCASION_SCORE = 2.0
WARMTH_SCORE = 1.5
WARMTH_TOLERANCE = 0.5


def target_warmth(t: float) -> float:
    """`clamp(1 + (30 - t) / 7, 1, 5.5)`，t 为体感温度。"""
    return max(1.0, min(5.5, 1 + (30 - t) / 7))


def band_ok(t: float, base: Item | None, mid: Item | None, outer: Item | None) -> bool:
    """某个温度下，这套上装厚度是否兼容（温度区间表）。"""
    if base is None or base.weight not in WARMTH:
        return True  # 数据不全时不判负
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
            it.weight in {"thin", "medium"}
            for it in (base, mid, outer)
            if it is not None
        )
    # <10°C：要求中层与外层够厚；内层不限（厚毛衣当内搭是正常穿法）
    return (
        mid is not None
        and outer is not None
        and mid.weight in {"medium", "thick"}
        and outer.weight in {"medium", "thick"}
    )


def band_label(t: float) -> str:
    if t >= 26:
        return "≥26°C 只内层"
    if t >= 18:
        return "18–26°C 单层或薄外套"
    if t >= 10:
        return "10–18°C 需中层或外套"
    return "<10°C 三层"


def _temps_for(t: float, tol: float) -> set[float]:
    """放宽档位下要检查的温度：当前值、±tol，以及被 tol 跨过的区间边界。"""
    temps = {t}
    if tol:
        temps |= {t - tol, t + tol}
    for boundary in BAND_BOUNDARIES:
        if t - tol <= boundary <= t + tol:
            temps.add(boundary)
    return temps


def rule_occ_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if ctx.feels_like is None:
        return RuleHit("R-OCC-01", HARD, SKIP)
    base = c.placement.get("base_top")
    mid = c.placement.get("mid_layer")
    outer = c.placement.get("outer_layer")
    if any(band_ok(t, base, mid, outer) for t in _temps_for(ctx.feels_like, tol)):
        return RuleHit("R-OCC-01", HARD, PASS)
    desc = " / ".join(
        f"{label} {it.weight}"
        for label, it in (("内", base), ("中", mid), ("外", outer))
        if it is not None
    )
    return RuleHit(
        "R-OCC-01", HARD, FAIL,
        reason=(
            f"体感 {ctx.feels_like:.1f}°C（{band_label(ctx.feels_like)}），"
            f"当前 {desc} 不兼容"
        ),
    )


def rule_occ_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom", "shoes"))
    if not main:
        return RuleHit("R-OCC-02", SOFT, SKIP)
    bounds = OCCASION_FORMALITY.get(ctx.occasion)
    if bounds is None:
        return RuleHit("R-OCC-02", SOFT, SKIP)
    lo, hi = bounds
    mean = sum(it.formality for it in main) / len(main)
    if lo <= mean <= hi:
        return RuleHit(
            "R-OCC-02", SOFT, PASS, OCCASION_SCORE,
            f"场合「{ctx.occasion}」，正式度均值 {mean:.1f}，落在 {lo:g}–{hi:g}",
        )
    return RuleHit("R-OCC-02", SOFT, SKIP)


def rule_occ_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if ctx.feels_like is None:
        return RuleHit("R-OCC-03", SOFT, SKIP)
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if not main or any(it.weight not in WARMTH for it in main):
        return RuleHit("R-OCC-03", SOFT, SKIP)
    mean = sum(WARMTH[it.weight] for it in main) / len(main)
    target = target_warmth(ctx.feels_like)
    if abs(mean - target) <= WARMTH_TOLERANCE:
        return RuleHit(
            "R-OCC-03", SOFT, PASS, WARMTH_SCORE,
            f"体感 {ctx.feels_like:.1f}°C，暖度目标 {target:.1f}，这套 {mean:.1f}，匹配",
        )
    return RuleHit("R-OCC-03", SOFT, SKIP)


RULES = (
    ("R-OCC-01", rule_occ_01),
    ("R-OCC-02", rule_occ_02),
    ("R-OCC-03", rule_occ_03),
)

__all__ = ["RULES", "band_label", "band_ok", "target_warmth"]
