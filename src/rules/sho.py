"""鞋与配饰模块（SHO）——3 条规则。

课程口径：鞋是整套的**定调器**。上身全是休闲装、脚上一双皮鞋，就互相拆台；
鞋的颜色跟上装或配饰呼应，整套会显得是"想过才穿的"。天气也是鞋的事——
麂皮和帆布遇水就废。

- R-SHO-01 硬：鞋的正式度与全身均值差 ≤ 1
- R-SHO-02 软：鞋与上装或配饰同色系，+1.5
- R-SHO-03 软：降水时麂皮/帆布/缎面 −1.5，皮革/橡胶/防水涂层 +1
  （`material` 缺失则跳过）
"""

from __future__ import annotations

from .color_math import delta_e_hex
from .types import Candidate, Context, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

SAFE_COLOR_DELTA_E = 25.0

RAIN_BAD = frozenset({"麂皮", "帆布", "缎面"})
RAIN_GOOD = frozenset({"皮革", "橡胶", "防水涂层"})


def rule_sho_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    shoe = c.placement.get("shoes")
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if shoe is None or not main:
        return RuleHit("R-SHO-01", HARD, SKIP)
    mean = sum(it.formality for it in main) / len(main)
    diff = abs(shoe.formality - mean)
    if diff > 1 + tol:
        return RuleHit(
            "R-SHO-01", HARD, FAIL,
            reason=f"{shoe.name}正式度 {shoe.formality}，全身均值 {mean:.1f}，差 {diff:.1f} > 1",
        )
    return RuleHit("R-SHO-01", HARD, PASS)


def rule_sho_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    shoe = c.placement.get("shoes")
    if shoe is None:
        return RuleHit("R-SHO-02", SOFT, SKIP)
    targets = c.items_in(("base_top", "mid_layer", "outer_layer", "accessory"))
    for item in targets:
        if item.id == shoe.id:
            continue
        if (
            item.hue_family == shoe.hue_family
            and delta_e_hex(item.color_hex, shoe.color_hex) < SAFE_COLOR_DELTA_E
        ):
            return RuleHit(
                "R-SHO-02", SOFT, PASS, 1.5,
                f"{shoe.name}与{item.name}同色系，整套有呼应",
            )
    return RuleHit("R-SHO-02", SOFT, SKIP)


def rule_sho_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    if not ctx.is_rainy:
        return RuleHit("R-SHO-03", SOFT, SKIP)
    shoe = c.placement.get("shoes")
    if shoe is None or not shoe.material:
        return RuleHit("R-SHO-03", SOFT, SKIP)
    if shoe.material in RAIN_BAD:
        return RuleHit(
            "R-SHO-03", SOFT, PASS, -1.5,
            f"降水天穿 {shoe.name}（{shoe.material}），容易湿",
        )
    if shoe.material in RAIN_GOOD:
        return RuleHit(
            "R-SHO-03", SOFT, PASS, 1.0,
            f"降水天穿 {shoe.name}（{shoe.material}），能应付",
        )
    return RuleHit("R-SHO-03", SOFT, SKIP)


RULES = (
    ("R-SHO-01", rule_sho_01),
    ("R-SHO-02", rule_sho_02),
    ("R-SHO-03", rule_sho_03),
)

__all__ = ["RAIN_BAD", "RAIN_GOOD", "RULES"]
