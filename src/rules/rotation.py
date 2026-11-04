"""每日建议的穿着轮换：只改排序，不改合规性（`02` §4.7）。

规则分数相同的组合，天气不变时每天会推同一套。这里按 `last_worn_at`
与最近的 `swap` 反馈算一个修正值，由 `solver` 叠加在得分上参与排序。
修正值可正可负，但**永远不参与硬规则**——被硬规则拒绝的组合不会被放行。

纯函数：不读数据库、不取当前日期。调用方把 `today` 与反馈事件传进来。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from .identity import outfit_hash
from .types import Item

# 今天或昨天穿过：−2.5 / 件
RECENT_PENALTY = -2.5
# 2–3 天前穿过：−1.0 / 件
NEAR_PENALTY = -1.0
# 久未穿：最多 +0.5 / 件，21 天到顶
FRESH_BONUS = 0.5
FRESH_CAP_DAYS = 21
# 最近被「再换」划过：最多 −4，14 天线性衰减到 0
SWAP_PENALTY = -4.0
SWAP_WINDOW_DAYS = 14


@dataclass(frozen=True)
class Rotation:
    """一套求解用的轮换修正表。"""

    item_adjustments: Mapping[int, float] = field(default_factory=dict)
    swap_penalties: Mapping[str, float] = field(default_factory=dict)

    def delta(self, garment_ids: Iterable[int]) -> float:
        ids = tuple(garment_ids)
        return sum(self.item_adjustments.get(item_id, 0.0) for item_id in ids) + (
            self.swap_penalties.get(outfit_hash(ids), 0.0)
        )


def parse_day(value: str | None) -> date | None:
    """把库里的日期文本转成 date；脏值当没穿过处理，不让它炸整个求解。"""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def recency_adjustment(last_worn: date | None, today: date) -> float:
    if last_worn is None:
        # 从没穿过就是久未穿
        return FRESH_BONUS
    days = max(0, (today - last_worn).days)
    if days <= 1:
        return RECENT_PENALTY
    if days <= 3:
        return NEAR_PENALTY
    return round(min(FRESH_BONUS, FRESH_BONUS * (days - 3) / (FRESH_CAP_DAYS - 3)), 2)


def swap_penalty(swapped_on: date, today: date) -> float:
    days = max(0, (today - swapped_on).days)
    if days >= SWAP_WINDOW_DAYS:
        return 0.0
    return round(SWAP_PENALTY * (1 - days / SWAP_WINDOW_DAYS), 2)


def build_rotation(
    items: Sequence[Item],
    swaps: Iterable[tuple[date, str]],
    today: date,
) -> Rotation:
    """`swaps` 是 (发生日期, 组合 hash)；同一组合只取最重的一次。"""
    adjustments = {
        item.id: recency_adjustment(parse_day(item.last_worn_at), today)
        for item in items
    }
    penalties: dict[str, float] = {}
    for swapped_on, hash_value in swaps:
        penalty = swap_penalty(swapped_on, today)
        if penalty < 0 and penalty < penalties.get(hash_value, 0.0):
            penalties[hash_value] = penalty
    return Rotation(item_adjustments=adjustments, swap_penalties=penalties)


__all__ = [
    "FRESH_BONUS",
    "NEAR_PENALTY",
    "RECENT_PENALTY",
    "Rotation",
    "SWAP_PENALTY",
    "SWAP_WINDOW_DAYS",
    "build_rotation",
    "parse_day",
    "recency_adjustment",
    "swap_penalty",
]
