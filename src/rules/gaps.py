"""缺口诊断（`02` 第九节）。

只统计真实求解结果，不新增判定规则：四个温度带各跑一次严格档求解，
得到去重前的 `C(b)` 与去重后的 `V(b)`，其余指标全部由这两份缓存派生。

`src/rules/` 的纯函数约束同样适用：本模块不碰数据库、不读文件、不调模型。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .color_math import delta_e_hex
from .occ import OCCASION_FORMALITY, rule_occ_02
from .registry import evaluate_hard
from .slots import SLOT_ORDER, enumerate_candidates, placements_of
from .solver import Assessment, assess, dedup
from .types import Context, Item, Status

MIN_CONFIRMED = 5
STRICT_LEVEL = 0

VALID_OUTFIT_MIN = 10
REQUIRED_SLOT_MIN = 4
OPTIONAL_SLOT_MIN = 2
DEP_THRESHOLD = 0.40
EDGE_THRESHOLD = 0.30
ISLAND_SPAN_OK = 0.50

FILL_MIN_TOTAL = 5
FILL_MIN_POSITIVE_BANDS = 2
FILL_MAX = 2

MAIN_SLOTS = ("base_top", "mid_layer", "outer_layer", "bottom", "shoes")
DIAGNOSED_SLOTS = MAIN_SLOTS + ("accessory",)
REQUIRED_SLOTS = frozenset({"base_top", "bottom", "shoes"})

SLOT_CN = {
    "base_top": "内搭",
    "mid_layer": "中层",
    "outer_layer": "外层",
    "bottom": "下装",
    "shoes": "鞋",
    "accessory": "配饰",
}
SLOT_CATEGORY = {
    "base_top": ("T恤", "inner"),
    "mid_layer": ("卫衣", "mid"),
    "outer_layer": ("外套", "outer"),
    "bottom": ("裤子", "bottom"),
    "shoes": ("鞋", "shoes"),
}
SLOT_NOUN = {
    "base_top": "T恤",
    "mid_layer": "卫衣",
    "outer_layer": "外套",
    "bottom": "直筒裤",
    "shoes": "鞋",
}
WEIGHT_ORDER = ("thin", "medium", "thick")
WEIGHT_CN = {"thin": "薄", "medium": "中厚", "thick": "厚"}
NEUTRAL_PALETTE = ("#141414", "#6B7280", "#1F2A44", "#E8E2D6")


@dataclass(frozen=True)
class Band:
    key: str
    label: str
    feels_like: float
    short: str


BANDS = (
    Band("cold", "<10°C", 5.0, "冷天"),
    Band("cool", "10–18°C", 14.0, "凉天"),
    Band("warm", "18–26°C", 22.0, "暖天"),
    Band("hot", "≥26°C", 30.0, "热天"),
)


@dataclass(frozen=True)
class SlotMetric:
    slot: str
    item_count: int
    minimum: int
    thin: float
    dependency: float
    driver_id: int | None
    driver_band: str | None
    used: int
    remain: int
    total: int
    severity: float

    @property
    def triggered(self) -> bool:
        return self.thin > 0 or self.dependency > DEP_THRESHOLD


# ---------------------------------------------------------------------------
# 基础统计
# ---------------------------------------------------------------------------


def _solve_bands(
    items: Sequence[Item],
) -> tuple[dict[str, list[Assessment]], dict[str, list[Assessment]]]:
    """四个温度带各解一次：`C` 是去重前严格档候选，`V` 是去重后的有效组合。"""
    candidates: dict[str, list[Assessment]] = {}
    valid: dict[str, list[Assessment]] = {}
    for band in BANDS:
        ctx = Context(occasion="日常", feels_like=band.feels_like)
        assessed = (assess(c, ctx) for c in enumerate_candidates(items))
        strict = [a for a in assessed if a is not None and a.level == STRICT_LEVEL]
        candidates[band.key] = strict
        valid[band.key] = dedup(strict, limit=len(strict))
    return candidates, valid


def _slot_items(items: Sequence[Item], slot: str) -> list[Item]:
    return [
        item
        for item in items
        if any(slot in placement for placement in placements_of(item))
    ]


def _count_of(assessments: Sequence[Assessment], item_id: int) -> int:
    return sum(1 for a in assessments if item_id in a.garment_ids)


def _dedup_without(
    candidates: Sequence[Assessment], item_id: int
) -> list[Assessment]:
    kept = [a for a in candidates if item_id not in a.garment_ids]
    return dedup(kept, limit=len(kept))


def _slot_metric(
    slot: str,
    items: Sequence[Item],
    candidates: dict[str, list[Assessment]],
    valid: dict[str, list[Assessment]],
) -> SlotMetric | None:
    owned = _slot_items(items, slot)
    if not owned and slot == "accessory":
        return None

    minimum = REQUIRED_SLOT_MIN if slot in REQUIRED_SLOTS else OPTIONAL_SLOT_MIN
    thin = max(0.0, (minimum - len(owned)) / minimum)

    best_dep = 0.0
    driver_id: int | None = None
    driver_band: str | None = None
    used = remain = total = 0
    for item in owned:
        for band in BANDS:
            outfits = valid[band.key]
            if not outfits:
                continue
            left = _dedup_without(candidates[band.key], item.id)
            dep = 1 - len(left) / len(outfits)
            if dep > best_dep:
                best_dep = dep
                driver_id = item.id
                driver_band = band.key
                used = _count_of(outfits, item.id)
                remain = len(left)
                total = len(outfits)

    dep_score = min(1.0, max(0.0, (best_dep - DEP_THRESHOLD) / DEP_THRESHOLD))
    return SlotMetric(
        slot=slot,
        item_count=len(owned),
        minimum=minimum,
        thin=thin,
        dependency=best_dep,
        driver_id=driver_id,
        driver_band=driver_band,
        used=used,
        remain=remain,
        total=total,
        severity=thin + dep_score,
    )


# ---------------------------------------------------------------------------
# 槽位瓶颈
# ---------------------------------------------------------------------------


def _tightest_first(metrics: Sequence[SlotMetric]) -> list[SlotMetric]:
    return sorted(metrics, key=lambda m: (m.item_count, -m.dependency, SLOT_ORDER.index(m.slot)))


def _detail(group: Sequence[SlotMetric], names: dict[int, str]) -> str:
    ordered = _tightest_first(group)
    head = ordered[0]
    labels = [SLOT_CN[m.slot] for m in ordered]
    name = names.get(head.driver_id, "") if head.driver_id is not None else ""
    if len(ordered) > 1:
        lead = f"{name}同时顶{'和'.join(labels)}；{labels[0]}只有 {head.item_count} 件"
    else:
        lead = f"{labels[0]}只有 {head.item_count} 件"

    band = next(b for b in BANDS if b.key == head.driver_band)
    if head.dependency > DEP_THRESHOLD and head.total:
        # 去重是贪心的：删掉一件可能让原先被跳过的候选补进来，
        # 所以「用到它的套数」与「总减少套数」不一定相等，两个数都照实给。
        pct = round(head.dependency * 100)
        return (
            f"{lead}，{band.short} {head.total} 套里有 {head.used} 套用到它；"
            f"去掉它后掉到 {head.remain} 套（-{pct}%）"
        )
    if head.total:
        return f"{lead}（下限 {head.minimum} 件）；{band.short} {head.total} 套里用到 {head.used} 套"
    return f"{lead}（下限 {head.minimum} 件）；当前四个温度带都没有严格档组合"


def _bottlenecks(
    items: Sequence[Item],
    candidates: dict[str, list[Assessment]],
    valid: dict[str, list[Assessment]],
) -> tuple[list[dict], list[str]]:
    metrics = [
        metric
        for slot in DIAGNOSED_SLOTS
        if (metric := _slot_metric(slot, items, candidates, valid)) is not None
        and metric.triggered
    ]

    groups: list[list[SlotMetric]] = []
    by_driver: dict[int, list[SlotMetric]] = {}
    for metric in metrics:
        if metric.driver_id is not None:
            by_driver.setdefault(metric.driver_id, []).append(metric)
        else:
            groups.append([metric])
    groups.extend(by_driver.values())

    names = {item.id: item.name for item in items}
    cards: list[dict] = []
    fill_slots: list[str] = []
    for group in groups:
        ordered = _tightest_first(group)
        head = ordered[0]
        card = {
            "slots": [m.slot for m in ordered],
            "labels": [SLOT_CN[m.slot] for m in ordered],
            "item_count": min(m.item_count for m in ordered),
            "dependency": round(max(m.dependency for m in ordered), 2),
            "driver_item_id": head.driver_id,
            "driver_band": head.driver_band,
            "severity": round(max(m.severity for m in ordered), 2),
            "detail": _detail(ordered, names),
        }
        if len(ordered) > 1:
            card["item_count_by_slot"] = {m.slot: m.item_count for m in ordered}
        cards.append(card)
        fill_slots.append(head.slot)

    cards.sort(key=lambda c: (-c["severity"], c["slots"][0]))
    return cards[:2], fill_slots[:2]


# ---------------------------------------------------------------------------
# 穿不进组合的单品
# ---------------------------------------------------------------------------


def _support(
    item: Item, band: str, items: Sequence[Item], valid: dict[str, list[Assessment]]
) -> float:
    outfits = valid[band]
    own = _count_of(outfits, item.id)
    if not own:
        return 0.0
    best = 0.0
    for placement in placements_of(item):
        peer_counts = [
            _count_of(outfits, peer.id)
            for peer in items
            if peer.id != item.id
            and any(p & placement for p in placements_of(peer))
            and _count_of(outfits, peer.id) > 0
        ]
        # 分母含自己：同槽只有一件时它的出场率就是 100%，不是 0
        best = max(best, own / max([own, *peer_counts]))
    return best


def _span_ok(item: Item, items: Sequence[Item]) -> float:
    if len(items) <= 1:
        return 1.0
    near = sum(1 for other in items if other.id != item.id and abs(other.formality - item.formality) <= 2)
    return near / (len(items) - 1)


def _dominant_rule(
    item: Item, items: Sequence[Item]
) -> tuple[str | None, str | None]:
    counts: Counter[str] = Counter()
    reasons: dict[str, str | None] = {}
    for band in BANDS:
        ctx = Context(occasion="日常", feels_like=band.feels_like)
        for candidate in enumerate_candidates(items, anchor=item):
            for rule_id, hit in evaluate_hard(candidate, ctx, 0.0).items():
                if hit.is_fail:
                    counts[rule_id] += 1
                    reasons.setdefault(rule_id, hit.reason)
    if not counts:
        return None, None
    rule_id = counts.most_common(1)[0][0]
    return rule_id, reasons.get(rule_id)


def _isolated(
    items: Sequence[Item],
    candidates: dict[str, list[Assessment]],
    valid: dict[str, list[Assessment]],
) -> list[dict]:
    found: list[tuple[int, dict]] = []
    for item in items:
        counts = {band.key: _count_of(valid[band.key], item.id) for band in BANDS}
        appeared = [band.key for band in BANDS if counts[band.key] > 0]
        support_values = {
            band: _support(item, band, items, valid) for band in appeared
        }
        span = _span_ok(item, items)

        if not placements_of(item):
            kind = "hard"
            support = 0.0
        elif not appeared:
            kind = "hard"
            support = 0.0
        elif all(value < EDGE_THRESHOLD for value in support_values.values()):
            kind = "edge"
            support = min(support_values.values())
        elif span < ISLAND_SPAN_OK:
            kind = "formality_island"
            support = span
        else:
            continue

        rule_id, reason = _dominant_rule(item, items)
        if kind == "hard":
            if not placements_of(item):
                detail = f"{item.name}没有可用的层级，进不了任何组合"
            else:
                detail = "没有任何严格档组合包含它"
        elif kind == "edge":
            detail = f"出场率只有同槽头名的 {round(support * 100)}%"
        else:
            detail = f"正式度 {item.formality}，与库内 {round((1 - span) * 100)}% 单品跨度 >2"
        if rule_id:
            detail += f"（主因 {rule_id}"
            detail += f"：{reason}）" if reason else "）"

        kind_order = {"hard": 0, "edge": 1, "formality_island": 2}[kind]
        found.append(
            (
                kind_order,
                {
                    "item_id": item.id,
                    "name": item.name,
                    "kind": kind,
                    "support": round(support, 2),
                    "dominant_rule": rule_id,
                    "detail": detail,
                },
            )
        )

    found.sort(key=lambda entry: (entry[0], entry[1]["support"], entry[1]["item_id"]))
    return [entry[1] for entry in found[:3]]


# ---------------------------------------------------------------------------
# 场合适配
# ---------------------------------------------------------------------------


def _occasions(
    items: Sequence[Item], valid: dict[str, list[Assessment]]
) -> list[dict]:
    rows: list[dict] = []
    for occasion, (lo, hi) in OCCASION_FORMALITY.items():
        best = 0.0
        passed = total = 0
        for band in BANDS:
            outfits = valid[band.key]
            ctx = Context(occasion=occasion, feels_like=band.feels_like)
            for outfit in outfits:
                main = outfit.candidate.items_in(MAIN_SLOTS)
                if main:
                    best = max(best, sum(it.formality for it in main) / len(main))
                if rule_occ_02(outfit.candidate, ctx, 0.0).status is Status.PASS:
                    passed += 1
            total += len(outfits)

        blocked = [
            slot
            for slot in MAIN_SLOTS
            if max((it.formality for it in _slot_items(items, slot)), default=0) < lo
        ]
        gap = best < lo
        rows.append(
            {
                "occasion": occasion,
                "best_formality": round(best, 2),
                "target": [lo, hi],
                "fit_rate": round(passed / total, 3) if total else 0.0,
                "blocked_slots": blocked,
                "severity": round(min(1.0, (lo - best) / 2), 2) if gap else 0.0,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 补齐模拟
# ---------------------------------------------------------------------------


def _nearest_palette(color_hex: str) -> str:
    return min(NEUTRAL_PALETTE, key=lambda color: delta_e_hex(color_hex, color))


def _prototype_colors(items: Sequence[Item]) -> tuple[str, str]:
    if not items:
        return NEUTRAL_PALETTE[0], NEUTRAL_PALETTE[1]
    counts = Counter(_nearest_palette(item.color_hex) for item in items)
    dominant = max(NEUTRAL_PALETTE, key=lambda color: (counts[color], -NEUTRAL_PALETTE.index(color)))
    missing = [color for color in NEUTRAL_PALETTE if counts[color] == 0 and color != dominant]
    rest = missing or [color for color in NEUTRAL_PALETTE if color != dominant]
    second = max(rest, key=lambda color: delta_e_hex(dominant, color))
    return dominant, second


def _prototype_formalities(items: Sequence[Item]) -> tuple[int, ...]:
    values = [item.formality for item in items]
    if not values:
        return (2, 3)
    lo = max(1, min(values) - 1)
    hi = min(5, max(values) + 1)
    candidates = list(range(lo, hi + 1))
    if len(candidates) > 3:
        mean = sum(values) / len(values)
        candidates = sorted(sorted(candidates, key=lambda v: (abs(v - mean), v))[:3])
    return tuple(candidates)


def _prototypes(items: Sequence[Item], slot: str, prototype_id: int) -> list[Item]:
    category, layer = SLOT_CATEGORY[slot]
    colors = _prototype_colors(_slot_items(items, slot))
    weights = ("medium",) if slot == "shoes" else WEIGHT_ORDER
    out: list[Item] = []
    for color in colors:
        for formality in _prototype_formalities(_slot_items(items, slot)):
            for weight in weights:
                out.append(
                    Item(
                        id=prototype_id,
                        name=f"中性色{SLOT_NOUN[slot]}",
                        category=category,
                        layers=(layer,),
                        formality=formality,
                        color_hex=color,
                        fit="regular",
                        pattern="solid",
                        weight=weight,
                    )
                )
    return out


def _unlock(
    prototype: Item,
    items: Sequence[Item],
    candidates: dict[str, list[Assessment]],
    valid: dict[str, list[Assessment]],
) -> dict[str, int]:
    out: dict[str, int] = {}
    for band in BANDS:
        ctx = Context(occasion="日常", feels_like=band.feels_like)
        added = [
            a
            for candidate in enumerate_candidates([*items, prototype], anchor=prototype)
            if (a := assess(candidate, ctx)) is not None and a.level == STRICT_LEVEL
        ]
        merged = dedup(
            [*candidates[band.key], *added],
            limit=len(candidates[band.key]) + len(added),
        )
        out[band.key] = len(merged) - len(valid[band.key])
    return out


def _fills(
    items: Sequence[Item],
    candidates: dict[str, list[Assessment]],
    valid: dict[str, list[Assessment]],
    slots: Sequence[str],
) -> list[dict]:
    prototype_id = max((item.id for item in items), default=0) + 1
    best_by_slot: list[dict] = []
    for slot in slots:
        best: dict | None = None
        for prototype in _prototypes(items, slot, prototype_id):
            unlock = _unlock(prototype, items, candidates, valid)
            total = sum(unlock.values())
            positive = sum(1 for value in unlock.values() if value > 0)
            if total < FILL_MIN_TOTAL or positive < FILL_MIN_POSITIVE_BANDS:
                continue
            row = {
                "slot": slot,
                "name": prototype.name,
                "formality": prototype.formality,
                "weight": prototype.weight,
                "color_hex": prototype.color_hex,
                "unlock": unlock,
                "total_unlock": total,
            }
            if best is None or total > best["total_unlock"]:
                best = row
        if best is not None:
            best_by_slot.append(best)

    best_by_slot.sort(key=lambda row: -row["total_unlock"])
    return best_by_slot[:FILL_MAX]


# ---------------------------------------------------------------------------
# 对外入口
# ---------------------------------------------------------------------------


def diagnose(items: Sequence[Item]) -> dict:
    """返回 `02` §9.8 的完整诊断结构。调用方负责只传 confirmed 单品。"""
    ordered = sorted(items, key=lambda item: item.id)
    basis = {
        "item_count": len(ordered),
        "sufficient": len(ordered) >= MIN_CONFIRMED,
        "strict": True,
        "bands": [],
    }
    if not basis["sufficient"]:
        return {
            "basis": basis,
            "bottlenecks": [],
            "isolated": [],
            "occasions": [],
            "fills": [],
        }

    candidates, valid = _solve_bands(ordered)
    basis["bands"] = [
        {
            "key": band.key,
            "label": band.label,
            "feels_like": band.feels_like,
            "valid_outfits": len(valid[band.key]),
            "min": VALID_OUTFIT_MIN,
        }
        for band in BANDS
    ]
    bottlenecks, fill_slots = _bottlenecks(ordered, candidates, valid)
    return {
        "basis": basis,
        "bottlenecks": bottlenecks,
        "isolated": _isolated(ordered, candidates, valid),
        "occasions": _occasions(ordered, valid),
        "fills": _fills(ordered, candidates, valid, fill_slots),
    }


__all__ = [
    "BANDS",
    "DEP_THRESHOLD",
    "EDGE_THRESHOLD",
    "MIN_CONFIRMED",
    "NEUTRAL_PALETTE",
    "REQUIRED_SLOT_MIN",
    "VALID_OUTFIT_MIN",
    "diagnose",
]
