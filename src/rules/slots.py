"""槽位展开与枚举。

`item.layers` 是多值，直接做笛卡尔积会产出「两条裤子」「连衣裙配裤子」
「只有外套没有上衣」这类组合，而且判断不了一套是否完整。所以先映射到身体槽位，
再按槽位枚举：

1. 每个槽位至多一件；连体装/西装套装一件占两槽，占用后该槽位不可再放
2. 必须覆盖 上衣 + 下装 + 鞋
3. 外层与中层可空，内层不可空（连体装除外，它自己占了上衣槽）
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .types import Candidate, Item

LAYER_TO_SLOT = {
    "inner": "base_top",
    "mid": "mid_layer",
    "outer": "outer_layer",
    "bottom": "bottom",
    "shoes": "shoes",
    "accessory": "accessory",
}
SLOT_ORDER = ("base_top", "mid_layer", "outer_layer", "bottom", "shoes", "accessory")
REQUIRED_SLOTS = frozenset({"base_top", "bottom", "shoes"})

# 一件占两槽的品类
CATEGORY_SLOTS = {
    "连体装": ("base_top", "bottom"),
    "西装套装": ("outer_layer", "bottom"),
}


def placements_of(item: Item) -> list[frozenset[str]]:
    """一件单品可以占哪些槽位。连体装/套装固定占两槽，其余按 `layers` 展开。"""
    if item.category in CATEGORY_SLOTS:
        return [frozenset(CATEGORY_SLOTS[item.category])]
    out: list[frozenset[str]] = []
    for layer in item.layers:
        slot = LAYER_TO_SLOT.get(layer)
        if slot is None:
            continue
        placement = frozenset({slot})
        if placement not in out:
            out.append(placement)
    return out


def solvable(item: Item) -> bool:
    """有没有任何可用槽位。配饰以外的无槽单品进不了任何组合。"""
    return bool(placements_of(item))


def _slots_union(items: Iterable[Item]) -> frozenset[str]:
    slots: set[str] = set()
    for item in items:
        for placement in placements_of(item):
            slots |= placement
    return frozenset(slots)


def enumerate_candidates(
    items: Sequence[Item], anchor: Item | None = None
) -> list[Candidate]:
    """枚举槽位合法的完整组合。

    `anchor` 非空时只枚举能补全它的组合，规则与评分路径与全量求解完全相同，
    区别只在枚举范围（见 `02` 4.2）。
    """
    ordered = sorted(items, key=lambda it: (-len(placements_of(it)), it.id))
    out: list[Candidate] = []

    def suffix_slots(rest: Sequence[Item]) -> list[frozenset[str]]:
        acc: list[frozenset[str]] = []
        union: set[str] = set()
        for item in reversed(rest):
            for placement in placements_of(item):
                union |= placement
            acc.append(frozenset(union))
        return list(reversed(acc))

    def rec(
        rest: Sequence[Item],
        idx: int,
        occupied: dict[str, Item],
        chosen: list[Item],
        suffix: list[frozenset[str]],
    ) -> None:
        if idx == len(rest):
            if REQUIRED_SLOTS <= occupied.keys():
                by_id = {it.id: it for it in chosen}
                out.append(
                    Candidate(
                        items=tuple(sorted(by_id.values(), key=lambda x: x.id)),
                        placement=dict(occupied),
                    )
                )
            return
        # 后面剩下的单品补不齐必需槽位 → 整枝剪掉
        if not (REQUIRED_SLOTS - occupied.keys()) <= suffix[idx]:
            return

        item = rest[idx]
        # 不放这件
        rec(rest, idx + 1, occupied, chosen, suffix)
        # 放这件：普通单品选一个槽位；连体装/套装同时占两个槽位
        for placement in placements_of(item):
            if any(slot in occupied for slot in placement):
                continue
            new_occupied = dict(occupied)
            for slot in placement:
                new_occupied[slot] = item
            rec(rest, idx + 1, new_occupied, chosen + [item], suffix)

    if anchor is None:
        rec(ordered, 0, {}, [], suffix_slots(ordered))
        return out

    if not placements_of(anchor):
        return []
    rest = [it for it in ordered if it.id != anchor.id]
    suffix = suffix_slots(rest)
    for placement in placements_of(anchor):
        occupied = {slot: anchor for slot in placement}
        rec(rest, 0, occupied, [anchor], suffix)
    return out


__all__ = [
    "CATEGORY_SLOTS",
    "LAYER_TO_SLOT",
    "REQUIRED_SLOTS",
    "SLOT_ORDER",
    "enumerate_candidates",
    "placements_of",
    "solvable",
]
