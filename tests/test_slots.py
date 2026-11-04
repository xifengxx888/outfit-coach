"""槽位展开与枚举的单测：组合必须完整、每槽至多一件、多槽单品只算一件。"""

from __future__ import annotations

from factories import layer_item, make_item
from src.rules.slots import enumerate_candidates, placements_of, solvable


def test_placements_follow_layers() -> None:
    assert placements_of(layer_item("base")) == [frozenset({"base_top"})]
    assert placements_of(layer_item("bottom")) == [frozenset({"bottom"})]
    assert placements_of(layer_item("accessory")) == [frozenset({"accessory"})]


def test_multi_layer_item_can_occupy_either_slot() -> None:
    jacket = make_item(id=5, category="夹克", layers=("mid", "outer"))
    assert placements_of(jacket) == [
        frozenset({"mid_layer"}),
        frozenset({"outer_layer"}),
    ]


def test_one_piece_categories_occupy_two_slots() -> None:
    dress = make_item(id=7, category="连体装", layers=("inner",))
    suit = make_item(id=8, category="西装套装", layers=("outer",))
    assert placements_of(dress) == [frozenset({"base_top", "bottom"})]
    assert placements_of(suit) == [frozenset({"outer_layer", "bottom"})]


def test_solvable_requires_at_least_one_slot() -> None:
    assert solvable(layer_item("base")) is True
    assert solvable(make_item(id=9, layers=())) is False


def test_minimal_wardrobe_yields_one_outfit() -> None:
    items = [
        layer_item("base"),
        layer_item("bottom"),
        layer_item("shoes"),
    ]
    candidates = enumerate_candidates(items)
    assert len(candidates) == 1
    assert set(candidates[0].placement) == {"base_top", "bottom", "shoes"}


def test_missing_shoes_yields_no_outfit() -> None:
    items = [layer_item("base"), layer_item("bottom")]
    assert enumerate_candidates(items) == []


def test_mid_or_outer_item_doubles_the_choices() -> None:
    # 一件「mid/outer 都可」的夹克：不穿、当中层、当外层 → 3 种
    jacket = make_item(id=5, category="夹克", layers=("mid", "outer"))
    items = [layer_item("base"), layer_item("bottom"), layer_item("shoes"), jacket]
    assert len(enumerate_candidates(items)) == 3


def test_two_bottoms_are_alternatives_not_a_stack() -> None:
    items = [
        layer_item("base"),
        layer_item("bottom"),
        layer_item("bottom", id=11, name="第二条裤子"),
        layer_item("shoes"),
    ]
    candidates = enumerate_candidates(items)
    assert len(candidates) == 2
    assert all(len([k for k in c.placement]) == 3 for c in candidates)


def test_dress_covers_base_and_bottom_at_once() -> None:
    dress = make_item(id=7, category="连体装", layers=("inner",))
    shoes = layer_item("shoes")
    candidates = enumerate_candidates([dress, shoes])
    assert len(candidates) == 1
    placement = candidates[0].placement
    assert placement["base_top"] is placement["bottom"] is dress
    assert candidates[0].ids == tuple(sorted((dress.id, shoes.id)))


def test_accessory_is_optional() -> None:
    items = [
        layer_item("base"),
        layer_item("bottom"),
        layer_item("shoes"),
        layer_item("accessory"),
    ]
    candidates = enumerate_candidates(items)
    assert len(candidates) == 2
    assert any("accessory" in c.placement for c in candidates)


def test_anchor_limits_enumeration_to_combinations_containing_it() -> None:
    base_a = layer_item("base")
    base_b = layer_item("base", id=12, name="第二件内搭")
    bottom = layer_item("bottom")
    shoes = layer_item("shoes")
    items = [base_a, base_b, bottom, shoes]

    anchored = enumerate_candidates(items, anchor=bottom)
    assert len(anchored) == 2
    assert all(bottom.id in c.ids for c in anchored)
    assert len({c.ids for c in anchored}) == 2


def test_anchor_without_any_slot_returns_nothing() -> None:
    unsolvable = make_item(id=9, layers=())
    items = [layer_item("base"), layer_item("bottom"), layer_item("shoes"), unsolvable]
    assert enumerate_candidates(items, anchor=unsolvable) == []
