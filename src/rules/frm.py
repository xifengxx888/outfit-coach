"""正式度模块（FRM）——2 条规则。

课程口径：正式度不是"贵不贵"，是"这套衣服出现在什么场合不会出错"。
1 运动 / 2 休闲 / 3 日常 / 4 商务休闲 / 5 正装。
一套里正式度跳得太大，看起来就像"上半身去开会、下半身去跑步"。

- R-FRM-01 硬：相邻层正式度差 ≤ 1
- R-FRM-02 硬：全身（上装 + 下装）正式度极差 ≤ 2

「是不是匹配场合」不在这里判，只由 R-OCC-02 判，避免两处定义打架。
"""

from __future__ import annotations

from .types import Candidate, Context, Kind, RuleHit, Status

HARD = Kind.HARD
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")
FRM_SPREAD_MAX = 2
FRM_ADJACENT_MAX = 1


def rule_frm_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = c.items_in(TOP_SLOTS)
    for a, b in zip(tops, tops[1:]):
        if abs(a.formality - b.formality) > FRM_ADJACENT_MAX + tol:
            return RuleHit(
                "R-FRM-01", HARD, FAIL,
                reason=(
                    f"{a.name}（{a.formality}）与 {b.name}（{b.formality}）"
                    f"正式度差 {abs(a.formality - b.formality)}"
                ),
            )
    return RuleHit("R-FRM-01", HARD, PASS)


def rule_frm_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    main = c.items_in(("base_top", "mid_layer", "outer_layer", "bottom"))
    if len(main) < 2:
        return RuleHit("R-FRM-02", HARD, SKIP)
    spread = max(it.formality for it in main) - min(it.formality for it in main)
    if spread > FRM_SPREAD_MAX + tol:
        return RuleHit(
            "R-FRM-02", HARD, FAIL, reason=f"全身正式度极差 {spread} > 2"
        )
    return RuleHit("R-FRM-02", HARD, PASS)


RULES = (("R-FRM-01", rule_frm_01), ("R-FRM-02", rule_frm_02))

__all__ = ["RULES"]
