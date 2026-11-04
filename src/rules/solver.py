"""组合求解：枚举 → 硬过滤 → 软评分 → 渐进放宽 → 多样性去重。

顺序不能反（`02` 4.3）：先过滤再评分，才能保证输出的每一套至少不违规；
排序先按放宽档位升序、同档再按得分降序，否则会出现「放宽的组合排在
全合规组合前面」。

槽位约束永不放宽——放宽后就不是一套衣服了。可放宽的只有程度类硬规则，
清单见 `registry._RELAXABLE_IDS`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .registry import evaluate_hard, evaluate_soft
from .rotation import Rotation
from .slots import enumerate_candidates
from .types import Candidate, Context, Item, RuleHit

# 档位 → 容差；档位 3 也不再放宽容差以外的规则
RELAX_TOLS = (0.0, 0.5, 1.0, 2.0)
# 每放宽一条规则扣的分（02 §4.4）
RELAX_PENALTY = {0: 0.0, 1: 1.0, 2: 2.0, 3: 4.0}
MAX_REASONS = 5
DEFAULT_LIMIT = 10
MAX_SHARED_ITEMS = 3


@dataclass(frozen=True)
class Assessment:
    """一套通过硬规则的组合，附带档位、得分与可读理由。"""

    candidate: Candidate
    level: int
    relaxed_rules: tuple[str, ...]
    score: float
    soft_hits: tuple[RuleHit, ...]
    reason: str

    @property
    def thumbs_up(self) -> list[str]:
        return [h.rule_id for h in self.soft_hits if h.is_scored and h.value > 0]

    @property
    def thumbs_down(self) -> list[str]:
        return [h.rule_id for h in self.soft_hits if h.is_scored and h.value < 0]

    @property
    def garment_ids(self) -> tuple[int, ...]:
        return self.candidate.ids


@dataclass(frozen=True)
class SolveResult:
    outfits: tuple[Assessment, ...]
    candidate_count: int
    level_counts: dict[int, int]
    # 去重后实际可用的组合数（最多统计到 offset+limit+1 条，够判断还有没有下一页）
    matched_count: int = 0
    has_more: bool = False

    @property
    def best_level(self) -> int | None:
        """最低的、有解可用的放宽档位。全灭时为 None。"""
        levels = [lv for lv, n in sorted(self.level_counts.items()) if n > 0]
        return levels[0] if levels else None

    @property
    def all_rejected(self) -> bool:
        """是这个条件下压根没有可用组合；翻到空页不算。"""
        return self.matched_count == 0


def _build_reason(soft: Sequence[RuleHit]) -> str:
    reasons = [h.reason for h in soft if h.reason and h.is_scored]
    return "；".join(reasons[:MAX_REASONS]) if reasons else "硬规则全部通过，软规则无命中"


def assess(candidate: Candidate, ctx: Context) -> Assessment | None:
    """找到这套组合能通过的最低放宽档位；任何一档都过不了则返回 None。"""
    strict = evaluate_hard(candidate, ctx, 0.0)
    for level, tol in enumerate(RELAX_TOLS):
        hard = strict if level == 0 else evaluate_hard(candidate, ctx, tol)
        if any(hit.is_fail for hit in hard.values()):
            continue
        # 只在严格档失败、放宽后通过、且规则本身可放宽时，才算「放宽了它」
        relaxed = tuple(
            rid
            for rid, hit in hard.items()
            if strict[rid].is_fail and not hit.is_fail
        )
        soft = tuple(evaluate_soft(candidate, ctx))
        score = sum(h.value for h in soft if h.is_scored) - len(relaxed) * RELAX_PENALTY[level]
        reason = _build_reason(soft)
        if relaxed:
            details = [
                f"{rid}：{strict[rid].reason or '未记录原因'}" for rid in relaxed
            ]
            reason = f"放宽 {level} 档（{'；'.join(details)}）：{reason}"
        return Assessment(
            candidate=candidate,
            level=level,
            relaxed_rules=relaxed,
            score=round(score, 2),
            soft_hits=soft,
            reason=reason,
        )
    return None


def rank_key(
    a: Assessment, rotation: Rotation | None = None
) -> tuple[int, float, tuple[int, ...]]:
    """档位优先，得分次之，最后按 id 保证结果稳定可复现。

    `rotation` 只叠加在得分上（每日建议用），档位边界不会被它跨过。
    """
    delta = rotation.delta(a.garment_ids) if rotation is not None else 0.0
    return (a.level, -(a.score + delta), a.garment_ids)


def dedup(
    assessments: Sequence[Assessment],
    limit: int = DEFAULT_LIMIT,
    max_shared: int = MAX_SHARED_ITEMS,
    rotation: Rotation | None = None,
) -> list[Assessment]:
    """多样性去重：与任何已选组合共享 ≥3 件就跳过（02 §4.5）。

    这是「看起来有 37 套」和「真的有 37 种穿法」的区别。
    """
    selected: list[Assessment] = []
    seen: set[tuple[int, ...]] = set()
    ordered = sorted(assessments, key=lambda a: rank_key(a, rotation))
    for a in ordered:
        if a.garment_ids in seen:
            continue
        ids = set(a.garment_ids)
        if any(len(ids & set(s.garment_ids)) >= max_shared for s in selected):
            continue
        seen.add(a.garment_ids)
        selected.append(a)
        if len(selected) >= limit:
            break
    return selected


def solve(
    items: Sequence[Item],
    ctx: Context,
    limit: int = DEFAULT_LIMIT,
    anchor: Item | None = None,
    offset: int = 0,
    rotation: Rotation | None = None,
) -> SolveResult:
    """全量求解或锚定求解。两种模式只差枚举范围，规则与评分路径完全相同。

    翻页只切去重后的序列：去重是前缀稳定的，所以第 N 页与一次性取
    N+limit 条再切片结果一致，不会因为分批而重排。

    `rotation` 是每日建议的穿着轮换修正，只改同档内的排序。
    """
    if offset < 0 or limit < 1:
        raise ValueError("offset 不能为负，limit 至少为 1")

    candidates = enumerate_candidates(items, anchor=anchor)
    accepted: list[Assessment] = []
    level_counts: dict[int, int] = {level: 0 for level in range(len(RELAX_TOLS))}
    for candidate in candidates:
        result = assess(candidate, ctx)
        if result is None:
            continue
        level_counts[result.level] += 1
        accepted.append(result)

    # 多取一条，用来判断后面还有没有；也保证前 offset+limit 条与不分页时一致
    selected = dedup(accepted, limit=offset + limit + 1, rotation=rotation)
    return SolveResult(
        outfits=tuple(selected[offset : offset + limit]),
        candidate_count=len(candidates),
        level_counts=level_counts,
        matched_count=len(selected),
        has_more=len(selected) > offset + limit,
    )


__all__ = [
    "Assessment",
    "DEFAULT_LIMIT",
    "RELAX_PENALTY",
    "RELAX_TOLS",
    "SolveResult",
    "assess",
    "dedup",
    "rank_key",
    "solve",
]
