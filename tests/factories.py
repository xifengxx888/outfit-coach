"""测试工厂：用最少的参数造出合法的单品与组合。

默认单品是「灰色合身纯色薄款内层 T 恤」，中性色，不触发任何软规则；
要测哪条规则就只改相关字段，让用例的意图一眼可见。
"""

from __future__ import annotations

from typing import Any

from src.rules.registry import HARD_RULES, SOFT_RULES
from src.rules.types import Candidate, Context, Item, RuleHit

GREY = "#808080"
DEFAULT_LAYERS = {
    "base": ("inner",),
    "mid": ("mid",),
    "outer": ("outer",),
    "bottom": ("bottom",),
    "shoes": ("shoes",),
    "accessory": ("accessory",),
}
DEFAULT_CATEGORY = {
    "base": "T恤",
    "mid": "卫衣",
    "outer": "夹克",
    "bottom": "裤子",
    "shoes": "鞋",
    "accessory": "配饰",
}
# 按槽位分配固定 id，测试里不必每次手写，也避免 id 撞车
DEFAULT_ID = {
    "base": 1,
    "bottom": 2,
    "shoes": 3,
    "mid": 4,
    "outer": 5,
    "accessory": 6,
}
RULE_FNS = {spec.rule_id: spec.fn for spec in (*HARD_RULES, *SOFT_RULES)}


def make_item(**overrides: Any) -> Item:
    fields: dict[str, Any] = {
        "id": 1,
        "name": "测试单品",
        "category": "T恤",
        "layers": ("inner",),
        "formality": 3,
        "color_hex": GREY,
        "fit": "regular",
        "pattern": "solid",
        "weight": "thin",
        "material": None,
        "collar": None,
        "length_cm": None,
    }
    fields.update(overrides)
    return Item(**fields)


def outfit(
    base: Item | None = None,
    mid: Item | None = None,
    outer: Item | None = None,
    bottom: Item | None = None,
    shoes: Item | None = None,
    accessory: Item | None = None,
) -> Candidate:
    """按槽位组装一套组合。未传的槽位留空（base/bottom/shoes 由调用方补齐）。"""
    base = base or make_item(id=1, category="T恤", layers=("inner",))
    bottom = bottom or make_item(
        id=2, name="测试裤子", category="裤子", layers=("bottom",), fit="regular"
    )
    shoes = shoes or make_item(
        id=3, name="测试鞋", category="鞋", layers=("shoes",), formality=2
    )
    placement: dict[str, Item] = {"base_top": base, "bottom": bottom, "shoes": shoes}
    if mid is not None:
        placement["mid_layer"] = mid
    if outer is not None:
        placement["outer_layer"] = outer
    if accessory is not None:
        placement["accessory"] = accessory
    unique = {it.id: it for it in placement.values()}
    return Candidate(
        items=tuple(sorted(unique.values(), key=lambda it: it.id)),
        placement=placement,
    )


def layer_item(slot: str, **overrides: Any) -> Item:
    """按层造一件单品，默认品类、层级与 id 与该层匹配。"""
    fields: dict[str, Any] = {
        "id": DEFAULT_ID[slot],
        "category": DEFAULT_CATEGORY[slot],
        "layers": DEFAULT_LAYERS[slot],
    }
    fields.update(overrides)
    return make_item(**fields)


def run_rule(
    rule_id: str,
    candidate: Candidate,
    ctx: Context | None = None,
    tol: float = 0.0,
) -> RuleHit:
    """按规则 id 跑一条规则。测试里写字符串 id，便于覆盖度扫描。"""
    return RULE_FNS[rule_id](candidate, ctx or Context(), tol)
