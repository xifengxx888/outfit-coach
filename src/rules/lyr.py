"""层次模块（LYR）——3 条规则。

课程口径：叠穿不是"多穿几件"，是**由外向里逐层变薄、逐层变短**。
反过来就出现"薄外套罩着厚毛衣"的臃肿感，或者三层一样长、看不出层次。

- R-LYR-01 硬：厚度 外层 ≥ 中层 ≥ 内层（允许同厚）
  放宽档位：档位 1/2 不额外放宽，只有档位 3（±2.0）允许外层比内层薄一级
- R-LYR-02 软：三层时相邻长度差 ≥ 5cm，+1.5（`length_cm` 缺失则跳过）
- R-LYR-03 软：任意两层领型重复（双高领 / 双连帽），−1.5
"""

from __future__ import annotations

from .types import WEIGHT_IDX, Candidate, Context, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")
LENGTH_STEP_CM = 5.0
REPEAT_COLLARS = {"高领", "连帽"}
# 只有档位 3 才允许外层薄一级（02 §4.4）
WEIGHT_RELAX_TOL = 1.5


def rule_lyr_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(TOP_SLOTS)
    if len(tops) < 2:
        return RuleHit("R-LYR-01", HARD, SKIP)
    if any(it.weight not in WEIGHT_IDX for it in tops):
        return RuleHit("R-LYR-01", HARD, SKIP)
    allowed_drop = -1 if tol >= WEIGHT_RELAX_TOL else 0
    for inner, outer in zip(tops, tops[1:]):
        if WEIGHT_IDX[outer.weight] - WEIGHT_IDX[inner.weight] < allowed_drop:
            return RuleHit(
                "R-LYR-01", HARD, FAIL,
                reason=f"{outer.name}（{outer.weight}）比 {inner.name}（{inner.weight}）薄，厚度倒挂",
            )
    return RuleHit("R-LYR-01", HARD, PASS)


def rule_lyr_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(TOP_SLOTS)
    if len(tops) < 3:
        return RuleHit("R-LYR-02", SOFT, SKIP)
    lengths = [it.length_cm for it in tops]
    if any(v is None for v in lengths):
        return RuleHit("R-LYR-02", SOFT, SKIP)
    diffs = [
        abs(a - b)  # type: ignore[operator]
        for a, b in zip(lengths, lengths[1:])
    ]
    if all(d >= LENGTH_STEP_CM for d in diffs):
        return RuleHit(
            "R-LYR-02", SOFT, PASS, 1.5,
            f"三层长度差 {diffs[0]:.0f}cm / {diffs[1]:.0f}cm，层次拉得开",
        )
    return RuleHit("R-LYR-02", SOFT, SKIP)


def rule_lyr_03(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(TOP_SLOTS)
    # 不限相邻层：高领内搭 + V 领中层 + 高领外套仍然是双高领
    for i, a in enumerate(tops):
        for b in tops[i + 1 :]:
            if a.collar and a.collar == b.collar and a.collar in REPEAT_COLLARS:
                return RuleHit(
                    "R-LYR-03", SOFT, PASS, -1.5,
                    f"{a.name}与{b.name}都是{a.collar}，领口重复",
                )
    return RuleHit("R-LYR-03", SOFT, SKIP)


RULES = (
    ("R-LYR-01", rule_lyr_01),
    ("R-LYR-02", rule_lyr_02),
    ("R-LYR-03", rule_lyr_03),
)

__all__ = ["RULES"]
