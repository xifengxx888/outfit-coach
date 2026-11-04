"""26 条规则的登记表与批量求值。

9 个模块各自的 `RULES` 在这里汇总。新增或删除规则必须同步改 `02` 第五节，
`RULE_NAMES` 与 `HARD_RULES + SOFT_RULES` 的一致性由模块级断言守住。

放宽口径（`02` 4.4）：只有「程度类」硬规则可放宽——
R-LYR-01 厚度、R-FRM-01/02 正式度、R-SHO-01 鞋差、R-OCC-01 温度兼容。
「关系类」硬规则（主色数、双宽双紧、大图案）永不放宽。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import col, frm, lyr, mat, occ, pat, prp, sho, siz
from .types import Candidate, Context, Kind, RuleHit

RuleFn = Callable[[Candidate, Context, float], RuleHit]

MODULES = (siz, col, frm, prp, lyr, mat, pat, sho, occ)

RULE_NAMES = {
    "R-SIZ-01": "上装合身",
    "R-SIZ-02": "下装合身",
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

_HARD_IDS = frozenset(
    {"R-COL-01", "R-COL-04", "R-FRM-01", "R-FRM-02", "R-PRP-01", "R-PRP-02",
     "R-LYR-01", "R-PAT-01", "R-SHO-01", "R-OCC-01"}
)
_RELAXABLE_IDS = frozenset(
    {"R-FRM-01", "R-FRM-02", "R-LYR-01", "R-SHO-01", "R-OCC-01"}
)


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    fn: RuleFn

    @property
    def relaxable(self) -> bool:
        return self.rule_id in _RELAXABLE_IDS


HARD_RULES: tuple[RuleSpec, ...] = tuple(
    RuleSpec(rid, fn)
    for module in MODULES
    for rid, fn in module.RULES
    if rid in _HARD_IDS
)
SOFT_RULES: tuple[RuleSpec, ...] = tuple(
    RuleSpec(rid, fn)
    for module in MODULES
    for rid, fn in module.RULES
    if rid not in _HARD_IDS
)

assert len(HARD_RULES) + len(SOFT_RULES) == 26, "规则总数必须是 26"
assert {s.rule_id for s in HARD_RULES} | {s.rule_id for s in SOFT_RULES} == set(
    RULE_NAMES
), "登记表与 RULE_NAMES 不一致"
assert _RELAXABLE_IDS <= {s.rule_id for s in HARD_RULES}, "可放宽规则必须是硬规则"


def evaluate_hard(c: Candidate, ctx: Context, tol: float = 0.0) -> dict[str, RuleHit]:
    """跑全部硬规则。不可放宽的规则恒按 `tol=0` 评估。"""
    return {
        spec.rule_id: spec.fn(c, ctx, tol if spec.relaxable else 0.0)
        for spec in HARD_RULES
    }


def evaluate_soft(c: Candidate, ctx: Context) -> list[RuleHit]:
    """跑全部软规则。软规则不受放宽档位影响。"""
    return [spec.fn(c, ctx, 0.0) for spec in SOFT_RULES]


def rule_kind(rule_id: str) -> Kind:
    return Kind.HARD if rule_id in _HARD_IDS else Kind.SOFT


__all__ = [
    "HARD_RULES",
    "MODULES",
    "RULE_NAMES",
    "SOFT_RULES",
    "RuleSpec",
    "evaluate_hard",
    "evaluate_soft",
    "rule_kind",
]
