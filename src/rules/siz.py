"""尺寸合身模块（SIZ）——2 条复合软规则。

课程口径：合不合身先看**肩线落点**，再看**胸围松量**，最后看**袖长**。
这些规则「有数据才判」：身体或衣件缺对应尺寸时，该维度直接跳过，
不扣分也不写空话；一个维度都判不了时整条 SKIP。

- R-SIZ-01 软：上装合身——肩线、胸围松量、袖长，−2.5 ~ +0.2
- R-SIZ-02 软：下装合身——臀围松量，−1.0 ~ +0.2

聚合按**维度**取最差的一件，不按件累加：正常叠穿（内层合身、外层略宽）
本来就该有一层松量，按件累加会把每一套三层搭配都扣到底。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .types import Candidate, Context, Item, Kind, RuleHit, Status

HARD, SOFT = Kind.HARD, Kind.SOFT
PASS, SKIP, FAIL = Status.PASS, Status.SKIP, Status.FAIL

# 身体数据来源 → 权重（docs/02）。只有身体字段的来源参与，衣件的录入方式不参与。
SOURCE_WEIGHT = {"body": 1.0, "garment": 0.85, "estimated": 0.5}
SOURCE_LABEL = {"estimated": "（估算）", "garment": "（量衣）"}

# 上装槽位，从内到外；同一件占多槽时取最外层（胸围区间最宽）
TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")
DIM_ORDER = ("shoulder", "chest", "sleeve")
DIM_LABEL = {"shoulder": "肩线", "chest": "胸围松量", "sleeve": "袖长"}
DIM_FIELD = {"shoulder": "shoulder_width", "chest": "chest", "sleeve": "arm_length"}

SHOULDER_GOOD_CM = 2.5
SHOULDER_NEUTRAL_CM = 7.0
SHOULDER_NARROW_PENALTY = -1.0
SHOULDER_DROP_PENALTY = -0.5

# 胸围松量合理区间（衣件平铺胸宽 ×2 − 身体胸围）：槽位 × 版型
CHEST_EASE = {
    "base_top": {"slim": (0.0, 8.0), "regular": (4.0, 12.0), "oversize": (10.0, 24.0)},
    "mid_layer": {"slim": (2.0, 10.0), "regular": (6.0, 16.0), "oversize": (12.0, 26.0)},
    "outer_layer": {"slim": (6.0, 14.0), "regular": (8.0, 20.0), "oversize": (14.0, 30.0)},
}
CHEST_TIGHT_PENALTY = -1.0
CHEST_LOOSE_PENALTY = -0.5
EASE_TOLERANCE_CM = 1.0

# 短袖本项目在 19.5–22cm，长袖 55.5–58cm；40 足够分开，短袖不判袖长
LONG_SLEEVE_MIN_CM = 40.0
SLEEVE_ALLOWED_CM = 8.0
SLEEVE_PENALTY = -0.5

HIP_TIGHT_PENALTY = -1.0
HIP_SNUG_BONUS = 0.1
HIP_GOOD_BONUS = 0.2
HIP_LOOSE_PENALTY = -0.3
HIP_TIGHT_CM = 0.0
HIP_SNUG_CM = 2.0
HIP_LOOSE_CM = 10.0
SIZ_02_FLOOR = -1.0

SIZ_01_FLOOR = -2.5
FIT_BONUS = 0.2


@dataclass(frozen=True)
class _Problem:
    """某个维度上最差的一件：单品、问题短语、加权后的扣分、身体字段名。"""

    item: Item
    label: str
    weighted: float
    field: str


def _num(value: float) -> str:
    """差值转文字：整数不带小数点，其余保留 1 位。"""
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _weight(ctx: Context, field_name: str) -> float:
    """按身体字段来源降权；来源缺失或未知按 1.0。"""
    return SOURCE_WEIGHT.get(ctx.body_sources.get(field_name, ""), 1.0)


def _suffix(ctx: Context, field_names: Iterable[str]) -> str:
    """理由末尾标注证据强度：估算优先，其次量衣；手量不标。"""
    labels = {SOURCE_LABEL.get(ctx.body_sources.get(f, ""), "") for f in field_names}
    for label in ("（估算）", "（量衣）"):
        if label in labels:
            return label
    return ""


def _tops(c: Candidate) -> list[tuple[str, Item]]:
    """上装件及其槽位；同一件占多槽时取最外层，避免被两个松量区间重复判负。"""
    out: list[tuple[str, Item]] = []
    index: dict[int, int] = {}
    for slot in TOP_SLOTS:
        item = c.placement.get(slot)
        if item is None:
            continue
        pos = index.get(item.id)
        if pos is not None:
            out[pos] = (slot, item)
            continue
        index[item.id] = len(out)
        out.append((slot, item))
    return out


def _shoulder(item: Item, ctx: Context) -> tuple[float, str] | None:
    if item.shoulder_cm is None or ctx.shoulder_cm is None:
        return None
    d = item.shoulder_cm - ctx.shoulder_cm
    if d < -SHOULDER_GOOD_CM:
        return SHOULDER_NARROW_PENALTY, f"肩线窄 {_num(-d)}cm，会绷"
    if d <= SHOULDER_GOOD_CM:
        return 0.0, ""
    if d <= SHOULDER_NEUTRAL_CM or item.fit == "oversize":
        return 0.0, ""
    return SHOULDER_DROP_PENALTY, f"肩宽落 {_num(d)}cm"


def _chest(item: Item, slot: str, ctx: Context) -> tuple[float, str] | None:
    if item.chest_width_cm is None or ctx.chest_cm is None:
        return None
    ease = item.chest_width_cm * 2.0 - ctx.chest_cm
    lo, hi = CHEST_EASE[slot][item.fit]
    if ease < lo - EASE_TOLERANCE_CM:
        return CHEST_TIGHT_PENALTY, f"胸围松量 {_num(ease)}cm，偏紧"
    if ease > hi + EASE_TOLERANCE_CM:
        return CHEST_LOOSE_PENALTY, f"胸围松量 {_num(ease)}cm，偏松"
    return 0.0, ""


def _sleeve(item: Item, ctx: Context) -> tuple[float, str] | None:
    if item.sleeve_cm is None or ctx.arm_cm is None:
        return None
    if item.sleeve_cm < LONG_SLEEVE_MIN_CM:
        return None  # 短袖不判袖长
    s = item.sleeve_cm - ctx.arm_cm
    if s < 0:
        return SLEEVE_PENALTY, f"袖长短 {_num(-s)}cm"
    if s > SLEEVE_ALLOWED_CM:
        return SLEEVE_PENALTY, f"袖长长 {_num(s)}cm"
    return 0.0, ""


def rule_siz_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    tops = _tops(c)
    if not tops:
        return RuleHit("R-SIZ-01", SOFT, SKIP)

    worst: dict[str, _Problem] = {}
    dim_weight: dict[str, float] = {}
    evaluated: set[int] = set()

    for slot, item in tops:
        checks = {
            "shoulder": _shoulder(item, ctx),
            "chest": _chest(item, slot, ctx),
            "sleeve": _sleeve(item, ctx),
        }
        for dim in DIM_ORDER:
            result = checks[dim]
            if result is None:
                continue
            weight = _weight(ctx, DIM_FIELD[dim])
            dim_weight[dim] = weight
            evaluated.add(item.id)
            penalty, label = result
            if penalty == 0.0:
                continue
            weighted = penalty * weight
            if dim not in worst or weighted < worst[dim].weighted:
                worst[dim] = _Problem(item, label, weighted, DIM_FIELD[dim])

    if not dim_weight:
        return RuleHit("R-SIZ-01", SOFT, SKIP)

    if not worst:
        # 全合身：奖励随证据强度衰减，估算字段会把 +0.2 压到 +0.1
        fields = [DIM_FIELD[d] for d in DIM_ORDER if d in dim_weight]
        dims = "、".join(DIM_LABEL[d] for d in DIM_ORDER if d in dim_weight)
        bonus = round(FIT_BONUS * min(dim_weight.values()), 2)
        reason = f"上装合身：{len(evaluated)} 件{dims}合适{_suffix(ctx, fields)}"
        return RuleHit("R-SIZ-01", SOFT, PASS, bonus, reason)

    value = max(SIZ_01_FLOOR, round(sum(p.weighted for p in worst.values()), 2))

    # 同一件的多个问题合并到一个短语，理由里只用「，」「、」
    grouped: dict[int, list[_Problem]] = {}
    for dim in DIM_ORDER:
        problem = worst.get(dim)
        if problem is not None:
            grouped.setdefault(problem.item.id, []).append(problem)
    ordered = sorted(grouped.values(), key=lambda ps: sum(p.weighted for p in ps))[:2]
    phrases = [ps[0].item.name + "、".join(p.label for p in ps) for ps in ordered]
    reason = f"上装合身：{'，'.join(phrases)}{_suffix(ctx, (p.field for p in worst.values()))}"
    return RuleHit("R-SIZ-01", SOFT, PASS, value, reason)


def rule_siz_02(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    bottom = c.placement.get("bottom")
    if bottom is None or bottom.hip_cm is None or ctx.hip_cm is None:
        return RuleHit("R-SIZ-02", SOFT, SKIP)

    ease = bottom.hip_cm * 2.0 - ctx.hip_cm
    if ease < HIP_TIGHT_CM:
        value, label = HIP_TIGHT_PENALTY, f"臀围松量 {_num(ease)}cm，坐下会绷"
    elif ease < HIP_SNUG_CM:
        value, label = HIP_SNUG_BONUS, f"臀围松量 {_num(ease)}cm，贴体"
    elif ease <= HIP_LOOSE_CM:
        value, label = HIP_GOOD_BONUS, f"臀围松量 {_num(ease)}cm，合适"
    else:
        value, label = HIP_LOOSE_PENALTY, f"臀围松量 {_num(ease)}cm，偏肥"

    value = max(SIZ_02_FLOOR, round(value * _weight(ctx, "hip"), 2))
    reason = f"下装合身：{label}{_suffix(ctx, ('hip',))}"
    return RuleHit("R-SIZ-02", SOFT, PASS, value, reason)


RULES = (
    ("R-SIZ-01", rule_siz_01),
    ("R-SIZ-02", rule_siz_02),
)

__all__ = ["RULES"]
