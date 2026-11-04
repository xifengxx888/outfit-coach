"""比例与轮廓模块（PRP）——4 条规则。

课程口径：衣服好不好看，先看**上下身的体量关系**，再看细节。
上下都宽 → 像一个方块；上下都紧 → 像被捆住。
一宽一窄才有轮廓。小个子还要看外套下摆落在哪。

- R-PRP-01 硬：禁止上 oversize + 下 oversize
- R-PRP-02 硬：禁止上 slim + 下 slim
- R-PRP-03 软：上宽下窄 或 上窄下宽（跨两级才算），+2
- R-PRP-04 软：身高 <170 且外套下摆 ≥ 身高 × 0.55 → 压身高，−1
  （需要 `height_cm` 与外套 `length_cm`，缺失则跳过）
"""

from __future__ import annotations

from .types import FIT_CN, FIT_IDX, Candidate, Context, Item, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

SHORT_HEIGHT_CM = 170.0
HEM_RATIO = 0.55


def _upper(c: Candidate) -> Item | None:
    """上半身的代表件：有外套看外套（它决定轮廓），否则看内层。"""
    return c.placement.get("outer_layer") or c.placement.get("base_top")


def rule_prp_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if upper is None or lower is None:
        return RuleHit("R-PRP-01", HARD, SKIP)
    if upper.fit == "oversize" and lower.fit == "oversize":
        return RuleHit("R-PRP-01", HARD, FAIL, reason="上宽下也宽，整体会垮")
    return RuleHit("R-PRP-01", HARD, PASS)


def rule_prp_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if upper is None or lower is None:
        return RuleHit("R-PRP-02", HARD, SKIP)
    if upper.fit == "slim" and lower.fit == "slim":
        return RuleHit("R-PRP-02", HARD, FAIL, reason="上紧下也紧，看着局促")
    return RuleHit("R-PRP-02", HARD, PASS)


def rule_prp_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    upper, lower = _upper(c), c.placement.get("bottom")
    if upper is None or lower is None:
        return RuleHit("R-PRP-03", SOFT, SKIP)
    # 「宽 = oversize、窄 = slim」；regular 与 slim 只差一级，不算宽窄对比
    if abs(FIT_IDX[upper.fit] - FIT_IDX[lower.fit]) >= 2:
        return RuleHit(
            "R-PRP-03", SOFT, PASS, 2.0,
            f"上装{FIT_CN[upper.fit]}、下装{FIT_CN[lower.fit]}，有宽窄对比",
        )
    return RuleHit("R-PRP-03", SOFT, SKIP)


def rule_prp_04(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if ctx.height_cm is None or ctx.height_cm >= SHORT_HEIGHT_CM:
        return RuleHit("R-PRP-04", SOFT, SKIP)
    outer = c.placement.get("outer_layer")
    if outer is None or outer.length_cm is None:
        return RuleHit("R-PRP-04", SOFT, SKIP)
    if outer.length_cm >= HEM_RATIO * ctx.height_cm:
        return RuleHit(
            "R-PRP-04", SOFT, PASS, -1.0,
            reason=(
                f"身高 {ctx.height_cm:.0f}cm，{outer.name}长 "
                f"{outer.length_cm:.0f}cm，下摆压身高"
            ),
        )
    return RuleHit("R-PRP-04", SOFT, SKIP)


RULES = (
    ("R-PRP-01", rule_prp_01),
    ("R-PRP-02", rule_prp_02),
    ("R-PRP-03", rule_prp_03),
    ("R-PRP-04", rule_prp_04),
)

__all__ = ["RULES"]
