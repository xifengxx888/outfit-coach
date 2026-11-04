"""规则引擎（纯函数，无 IO）。

对外的入口只有这几个：

    from src.rules import Item, Context, solve, assess

    result = solve(items, Context(occasion="日常", feels_like=15, height_cm=175))
    for outfit in result.outfits:
        print(outfit.score, outfit.reason)

规则引擎**不 import `src/db` 或 `src/api`**，也不读文件、不调模型：
输入是单品与上下文，输出是组合与得分。这样才能单测、才能被 M3 的课程复用。
"""

from .color_math import ColorAttrs, color_attrs, delta_e_hex
from .registry import HARD_RULES, RULE_NAMES, SOFT_RULES, evaluate_hard, evaluate_soft
from .slots import enumerate_candidates, placements_of
from .solver import Assessment, SolveResult, assess, solve
from .types import Candidate, Context, Item, Kind, Occasion, RuleHit, Status

__all__ = [
    "Assessment",
    "Candidate",
    "ColorAttrs",
    "Context",
    "HARD_RULES",
    "Item",
    "Kind",
    "Occasion",
    "RULE_NAMES",
    "RuleHit",
    "SOFT_RULES",
    "SolveResult",
    "Status",
    "assess",
    "color_attrs",
    "delta_e_hex",
    "enumerate_candidates",
    "evaluate_hard",
    "evaluate_soft",
    "placements_of",
    "solve",
]
