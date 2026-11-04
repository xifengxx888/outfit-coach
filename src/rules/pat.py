"""图案模块（PAT）——2 条规则。

课程口径：全身只能有一个视觉焦点。大图案（条纹、字母、格纹）本身就是主角，
两件一起穿会互相抢；而图案落在**视觉主体位**（外套或下装）时，
其余纯色反而是把焦点托起来。

- R-PAT-01 硬：全身 `pattern=bold` 最多一件
- R-PAT-02 软：唯一的大图案在外层或下装、其余全纯色，+1
"""

from __future__ import annotations

from .types import Candidate, Context, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

VISUAL_SLOTS = ("outer_layer", "bottom")


def rule_pat_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bold = [it for it in c.items if it.pattern == "bold"]
    if len(bold) > 1:
        return RuleHit(
            "R-PAT-01", HARD, FAIL,
            reason=f"大图案有 {len(bold)} 件（{'、'.join(it.name for it in bold)}），超过 1 件",
        )
    return RuleHit("R-PAT-01", HARD, PASS)


def rule_pat_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bold = [it for it in c.items if it.pattern == "bold"]
    if len(bold) != 1:
        return RuleHit("R-PAT-02", SOFT, SKIP)
    item = bold[0]
    in_visual = any(c.placement.get(slot) is item for slot in VISUAL_SLOTS)
    others_solid = all(
        it.pattern == "solid" for it in c.items if it.id != item.id
    )
    if in_visual and others_solid:
        return RuleHit(
            "R-PAT-02", SOFT, PASS, 1.0,
            f"图案在{item.name}上，其余纯色，视觉有主次",
        )
    return RuleHit("R-PAT-02", SOFT, SKIP)


RULES = (("R-PAT-01", rule_pat_01), ("R-PAT-02", rule_pat_02))

__all__ = ["RULES"]
