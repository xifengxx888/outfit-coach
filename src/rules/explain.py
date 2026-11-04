"""解释层：把规则命中翻译成「有依据的搭配解释」。

`reason` 回答「哪条规则加了分」，本模块回答「这套为什么成立、依据是什么、
下次自己怎么看」。它只读 `Assessment` 与 `Context`，不重算分数、不改等级、
不调模型，也不进入 `solve()` / `assess()` 的热路径。

三条硬边界：

1. 正向原理只来自 `is_scored and value > 0` 的软命中；
2. 放宽、负向扣分、上下文偏差只进 `caveats`，绝不包装成正向行；
3. `dormant` / `boundary` 原理不生成正向行，缺数据不补空话。
"""

from __future__ import annotations

from dataclasses import dataclass

from .col import BLUR_DELTA_E, BODY_SLOTS, color_pairs
from .color_math import delta_e_hex
from .occ import OCCASION_FORMALITY, WARMTH_TOLERANCE, target_warmth
from .registry import SOFT_RULES, evaluate_hard
from .solver import Assessment
from .theory import AXIS_ORDER, PRINCIPLE_BY_ID, Principle
from .types import (
    FIT_CN,
    FIT_IDX,
    WARMTH,
    Candidate,
    Context,
    Item,
    Status,
)

VERSION = "explain-v1"
MAX_LINES = 5
MAX_PER_AXIS = 2
MAX_CAVEATS = 3
MAX_GAPS = 2
LONG_SLEEVE_MIN_CM = 40.0
TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")
MAIN_SLOTS = ("base_top", "mid_layer", "outer_layer", "bottom", "shoes")
WEIGHT_CN = {"thin": "薄", "medium": "中", "thick": "厚"}

# 软规则 → 原理 ID。只列能产生正向证据的规则；负向规则不在此表。
LINE_SPECS: tuple[tuple[str, str], ...] = (
    ("R-PRP-03", "P-VIS-01"),
    ("R-COL-03", "P-COL-02"),
    ("R-COL-06", "P-COL-03"),
    ("R-SHO-02", "P-COL-06"),
    ("R-SIZ-01", "P-FIT-01"),
    ("R-SIZ-02", "P-FIT-02"),
    ("R-LYR-02", "P-LAY-02"),
    ("R-OCC-02", "P-SOC-02"),
    ("R-OCC-03", "P-SOC-03"),
    ("R-SHO-03", "P-SOC-03"),
    ("R-MAT-01", "P-TEX-01"),
    ("R-PAT-02", "P-PAT-01"),
)
LINE_BY_RULE = dict(LINE_SPECS)
_SOFT_ORDER = {spec.rule_id: i for i, spec in enumerate(SOFT_RULES)}
_AXIS_ORDER = {axis: i for i, axis in enumerate(AXIS_ORDER)}
_BLOCKED_STATUSES = frozenset({"dormant", "boundary"})


@dataclass(frozen=True)
class ExplanationLine:
    principle_id: str
    rule_id: str
    title: str
    evidence: str
    why: str
    how_to_judge: str
    grade: str
    grade_label: str
    source: str
    source_url: str | None
    kind: str = "principle"  # principle | baseline


@dataclass(frozen=True)
class Caveat:
    code: str  # relaxed | negative_soft | context
    text: str
    rule_id: str | None
    severity: str = "info"  # info | warn


@dataclass(frozen=True)
class StyleProfile:
    label: str
    inferred: bool
    formality_band: str
    silhouette: str
    color_tendency: str
    basis: str
    caveat: str


@dataclass(frozen=True)
class Explanation:
    headline: str
    principles: tuple[ExplanationLine, ...]
    caveats: tuple[Caveat, ...]
    style: StyleProfile
    data_gaps: tuple[str, ...]
    version: str = VERSION


@dataclass(frozen=True)
class _CandidateLine:
    principle: Principle
    rule_id: str
    evidence: str
    value: float
    order: int


def _num(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def _line(
    principle: Principle,
    rule_id: str,
    evidence: str,
    kind: str = "principle",
) -> ExplanationLine:
    return ExplanationLine(
        principle_id=principle.id,
        rule_id=rule_id,
        title=principle.title,
        evidence=evidence,
        why=principle.why,
        how_to_judge=principle.how_to_judge,
        grade=principle.grade,
        grade_label=principle.grade_label,
        source=principle.source,
        source_url=principle.source_url,
        kind=kind,
    )


# ---------------------------------------------------------------------------
# 正向原理行
# ---------------------------------------------------------------------------


def _positive_lines(assessment: Assessment) -> dict[str, _CandidateLine]:
    """取正向软命中，按 P-ID 去重，保留分值最高的一条（同分保留规则顺序在前）。"""
    best: dict[str, _CandidateLine] = {}
    for index, hit in enumerate(assessment.soft_hits):
        if not hit.is_scored or hit.value <= 0 or not hit.reason:
            continue
        principle_id = LINE_BY_RULE.get(hit.rule_id)
        if principle_id is None:
            continue
        principle = PRINCIPLE_BY_ID[principle_id]
        if principle.status in _BLOCKED_STATUSES:
            continue
        candidate = _CandidateLine(
            principle=principle,
            rule_id=hit.rule_id,
            evidence=hit.reason,
            value=hit.value,
            order=_SOFT_ORDER.get(hit.rule_id, index),
        )
        previous = best.get(principle_id)
        if previous is None or (candidate.value, -candidate.order) > (
            previous.value,
            -previous.order,
        ):
            best[principle_id] = candidate
    return best


def _select_lines(best: dict[str, _CandidateLine]) -> list[_CandidateLine]:
    """按轴顺序选 1–5 条；同一轴最多 2 条；有合身证据时预留 1 个位置。"""
    ordered = sorted(
        best.values(),
        key=lambda line: (
            _AXIS_ORDER[line.principle.axis],
            -line.value,
            line.order,
        ),
    )
    chosen: list[_CandidateLine] = []
    axis_count: dict[str, int] = {}
    fit = [line for line in ordered if line.principle.axis == "fit"]
    if fit:
        chosen.append(fit[0])
        axis_count["fit"] = 1
    for line in ordered:
        if len(chosen) >= MAX_LINES:
            break
        if line.principle.id in {c.principle.id for c in chosen}:
            continue
        axis = line.principle.axis
        if axis_count.get(axis, 0) >= MAX_PER_AXIS:
            continue
        chosen.append(line)
        axis_count[axis] = axis_count.get(axis, 0) + 1
    chosen.sort(
        key=lambda line: (
            _AXIS_ORDER[line.principle.axis],
            -line.value,
            line.order,
        )
    )
    return chosen


def _tops(candidate: Candidate) -> list[Item]:
    return candidate.items_in(TOP_SLOTS)


def _main(candidate: Candidate, slots: tuple[str, ...] = MAIN_SLOTS) -> list[Item]:
    return candidate.items_in(slots)


def _baseline_line(
    assessment: Assessment,
    chosen: list[_CandidateLine],
) -> ExplanationLine | None:
    """正向行不足 2 条时补 1 条结构底线；只陈述硬规则已通过的事实。"""
    candidate = assessment.candidate
    tops = _tops(candidate)
    axes = {line.principle.axis for line in chosen}

    # P-LAY-01：两层及以上，厚度由内到外没有倒挂（R-LYR-01 严格档通过）
    if "layer" not in axes and len(tops) >= 2 and all(
        it.weight in WEIGHT_CN for it in tops
    ):
        idx = [list(WEIGHT_CN).index(it.weight) for it in tops]
        if all(b >= a for a, b in zip(idx, idx[1:])):
            names = ("内层", "外层") if len(tops) == 2 else ("内层", "中层", "外层")
            layers = " / ".join(
                f"{name}{WEIGHT_CN[it.weight]}" for name, it in zip(names, tops)
            )
            return _line(
                PRINCIPLE_BY_ID["P-LAY-01"],
                "R-LYR-01",
                f"{layers}，厚度由内到外没有倒挂",
                "baseline",
            )

    # P-COL-01：只判「不同色系却糊在一起」，同色同色相不适用
    if "color" not in axes:
        pairs = [
            (a, b)
            for a, b in color_pairs(candidate)
            if a.hue_family != b.hue_family
        ]
        if pairs:
            deltas = [delta_e_hex(a.color_hex, b.color_hex) for a, b in pairs]
            low = min(deltas)
            if low >= BLUR_DELTA_E:
                verdict = "达到可辨阈值 10，颜色没有糊在一起"
            else:
                verdict = "低于可辨阈值 10，颜色区分偏弱"
            return _line(
                PRINCIPLE_BY_ID["P-COL-01"],
                "R-COL-02",
                f"相邻异色系最小 ΔE00={low:.1f}，{verdict}",
                "baseline",
            )

    # P-SOC-01：鞋没有单独跳出全身正式度（严格档口径）
    shoe = candidate.placement.get("shoes")
    body = _main(candidate, ("base_top", "mid_layer", "outer_layer", "bottom"))
    if (
        "social" not in axes
        and shoe is not None
        and body
        and not any(line.principle.id == "P-COL-06" for line in chosen)
    ):
        mean = sum(it.formality for it in body) / len(body)
        diff = abs(shoe.formality - mean)
        if diff <= 1.0:
            return _line(
                PRINCIPLE_BY_ID["P-SOC-01"],
                "R-SHO-01",
                f"{shoe.name}正式度 {shoe.formality}，其余 {len(body)} 件均值 {mean:.2f}，差 {_num(diff)}，没有抢调",
                "baseline",
            )
    return None


# ---------------------------------------------------------------------------
# 注意事项
# ---------------------------------------------------------------------------


def _context_caveats(assessment: Assessment, ctx: Context) -> list[Caveat]:
    """OCC-02/03 为 SKIP 时，直接从 candidate/ctx 复算偏差（SKIP 没有 reason）。"""
    hits = {hit.rule_id: hit for hit in assessment.soft_hits}
    candidate = assessment.candidate
    out: list[Caveat] = []

    occ2 = hits.get("R-OCC-02")
    body = _main(candidate)
    bounds = OCCASION_FORMALITY.get(ctx.occasion)
    if occ2 is not None and occ2.status is Status.SKIP and body and bounds:
        mean = sum(it.formality for it in body) / len(body)
        lo, hi = bounds
        if not lo <= mean <= hi:
            distance = lo - mean if mean < lo else mean - hi
            out.append(
                Caveat(
                    "context",
                    f"场合「{ctx.occasion}」要求正式度 {lo:g}–{hi:g}，这套均值 {mean:.2f}，差 {_num(distance)}",
                    "R-OCC-02",
                    "warn" if distance > 1.0 else "info",
                )
            )

    occ3 = hits.get("R-OCC-03")
    warm_items = _main(candidate, ("base_top", "mid_layer", "outer_layer", "bottom"))
    if (
        occ3 is not None
        and occ3.status is Status.SKIP
        and ctx.feels_like is not None
        and warm_items
        and all(it.weight in WARMTH for it in warm_items)
    ):
        mean = sum(WARMTH[it.weight] for it in warm_items) / len(warm_items)
        target = target_warmth(ctx.feels_like)
        distance = abs(mean - target)
        if distance > WARMTH_TOLERANCE:
            out.append(
                Caveat(
                    "context",
                    f"体感 {ctx.feels_like:.1f}°C 的暖度目标 {target:.1f}，这套 {mean:.1f}，差 {_num(distance)}",
                    "R-OCC-03",
                    "warn" if distance > 1.0 else "info",
                )
            )
    return out


def _caveats(assessment: Assessment, ctx: Context) -> tuple[Caveat, ...]:
    out: list[Caveat] = []
    if assessment.level > 0 and assessment.relaxed_rules:
        strict = evaluate_hard(assessment.candidate, ctx, 0.0)
        details = "；".join(
            f"{rid}（{strict[rid].reason or '严格档未通过'}）"
            for rid in assessment.relaxed_rules
        )
        out.append(
            Caveat(
                "relaxed",
                f"放宽 {assessment.level} 档才成立：{details}",
                None,
                "warn",
            )
        )
    for hit in assessment.soft_hits:
        if hit.is_scored and hit.value < 0 and hit.reason:
            out.append(
                Caveat(
                    "negative_soft",
                    f"{hit.reason}（{hit.value:g}）",
                    hit.rule_id,
                    "warn",
                )
            )
    out.extend(_context_caveats(assessment, ctx))
    return tuple(out[:MAX_CAVEATS])


# ---------------------------------------------------------------------------
# 风格推断（只描述，不计分）
# ---------------------------------------------------------------------------


def _formality_band(mean: float) -> str:
    if mean < 1.7:
        return "运动休闲"
    if mean < 2.5:
        return "日常休闲"
    if mean < 3.3:
        return "日常通勤"
    if mean < 4.2:
        return "商务休闲"
    return "正式"


def _silhouette(candidate: Candidate) -> str:
    upper = candidate.placement.get("outer_layer") or candidate.placement.get("base_top")
    lower = candidate.placement.get("bottom")
    if upper is None or lower is None:
        return "未判定"
    diff = FIT_IDX[upper.fit] - FIT_IDX[lower.fit]
    if diff >= 2:
        return "上宽下窄"
    if diff <= -2:
        return "上窄下宽"
    if upper.fit == lower.fit == "oversize":
        return "上下同宽"
    if upper.fit == lower.fit == "slim":
        return "上下同紧"
    return "上下均衡"


def _color_tendency(candidate: Candidate) -> tuple[str, int, int, int, float]:
    """返回（倾向、中性件数、总件数、主色数、饱和度合计）。"""
    body = _main(candidate, BODY_SLOTS)
    total = len(body)
    neutrals = sum(1 for it in body if it.is_neutral)
    families = {it.hue_family for it in body if it.colors.is_main_color}
    saturation = sum(it.saturation for it in body)
    ratio = neutrals / total if total else 0.0
    if not families:
        tendency = "中性色主导"
    elif len(families) == 1 and ratio >= 0.5:
        tendency = "一个主色 + 中性色"
    elif len(families) >= 2:
        tendency = "多主色"
    else:
        tendency = "低饱和"
    return tendency, neutrals, total, len(families), saturation


def _style(assessment: Assessment, ctx: Context) -> StyleProfile:
    candidate = assessment.candidate
    body = _main(candidate)
    mean = sum(it.formality for it in body) / len(body) if body else 0.0
    band = _formality_band(mean)
    silhouette = _silhouette(candidate)
    tendency, neutrals, total, color_count, saturation = _color_tendency(candidate)
    tops = _tops(candidate)
    upper = candidate.placement.get("outer_layer") or candidate.placement.get("base_top")
    lower = candidate.placement.get("bottom")
    upper_fit = FIT_CN.get(upper.fit, "未判定") if upper else "未判定"
    lower_fit = FIT_CN.get(lower.fit, "未判定") if lower else "未判定"
    light = [it.lightness for it in _main(candidate, BODY_SLOTS)]
    span = max(light) - min(light) if light else 0.0
    ratio = neutrals / total if total else 0.0

    suffix = ""
    if band == "运动休闲":
        suffix = "（偏运动休闲）"
    elif not color_count and ratio >= 0.85 and saturation < 60:
        suffix = "（偏极简）"
    elif band == "日常通勤":
        suffix = "（偏通勤）"

    depth = "三层" if len(tops) >= 3 else "两层" if len(tops) == 2 else "单层"
    basis = (
        f"正式度均值 {mean:.2f}（{band}）；上装{upper_fit} / 下装{lower_fit}；"
        f"{neutrals}/{total} 件中性色，{color_count} 个主色，"
        f"饱和度合计 {saturation:.0f}，明度跨度 {span:.0f}，{depth}"
    )
    return StyleProfile(
        label=f"{ctx.occasion} · {silhouette} · {tendency}{suffix}",
        inferred=True,
        formality_band=band,
        silhouette=silhouette,
        color_tendency=tendency,
        basis=basis,
        caveat="没有风格标签、配饰、鞋型数据，仅按正式度/廓形/色彩/层次推断，不参与评分。",
    )


# ---------------------------------------------------------------------------
# 结论
# ---------------------------------------------------------------------------


def _phrase(line: ExplanationLine, style: StyleProfile, ctx: Context) -> str | None:
    mapping = {
        "P-VIS-01": style.silhouette,
        "P-COL-02": "同色系深浅",
        "P-COL-03": "中性色打底",
        "P-COL-06": "鞋色与上身呼应",
        "P-FIT-01": "上装合身",
        "P-FIT-02": "下装合身",
        "P-LAY-01": "厚度由内到外递增",
        "P-LAY-02": "三层层次拉开",
        "P-SOC-02": f"{ctx.occasion}正式度刚好",
        "P-SOC-03": "雨天鞋材质能应付" if ctx.is_rainy else "暖度与体感匹配",
        "P-TEX-01": "材质有对比",
        "P-PAT-01": "图案有主次",
    }
    return mapping.get(line.principle_id)


def _transition(caveats: tuple[Caveat, ...], level: int) -> str:
    if level > 0:
        return f"放宽 {level} 档后能穿"
    notes: list[str] = []
    for caveat in caveats:
        if caveat.code == "context" and caveat.rule_id == "R-OCC-02":
            notes.append("正式度与场合有偏差")
        elif caveat.code == "context" and caveat.rule_id == "R-OCC-03":
            notes.append("暖度与体感有偏差")
    if notes:
        return "，".join(dict.fromkeys(notes))
    negative = sum(1 for caveat in caveats if caveat.code == "negative_soft")
    if negative:
        return f"另有 {negative} 项小扣分"
    return ""


def _headline(
    lines: tuple[ExplanationLine, ...],
    style: StyleProfile,
    caveats: tuple[Caveat, ...],
    ctx: Context,
    level: int,
) -> str:
    prefix = (
        f"{ctx.feels_like:.0f}°C {ctx.occasion}"
        if ctx.feels_like is not None
        else ctx.occasion
    )
    if ctx.is_rainy:
        prefix += "，有雨"
    phrases: list[str] = []
    for line in lines:
        phrase = _phrase(line, style, ctx)
        if phrase and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) >= 3:
            break
    body = "，".join(phrases) if phrases else "这套没有明显加分项，胜在硬约束都通过"
    tail = _transition(caveats, level)
    return f"{prefix}：{body}{'；' + tail if tail else ''}。"


# ---------------------------------------------------------------------------
# 数据缺口
# ---------------------------------------------------------------------------


def _data_gaps(assessment: Assessment, ctx: Context) -> tuple[str, ...]:
    candidate = assessment.candidate
    tops = _tops(candidate)
    gaps: list[str] = []

    missing_body: list[str] = []
    if ctx.shoulder_cm is None and any(it.shoulder_cm is not None for it in tops):
        missing_body.append("肩宽")
    if ctx.chest_cm is None and any(it.chest_width_cm is not None for it in tops):
        missing_body.append("胸围")
    bottom = candidate.placement.get("bottom")
    if ctx.hip_cm is None and bottom is not None and bottom.hip_cm is not None:
        missing_body.append("臀围")
    if ctx.arm_cm is None and any(
        it.sleeve_cm is not None and it.sleeve_cm >= LONG_SLEEVE_MIN_CM
        for it in tops
    ):
        missing_body.append("臂长")
    if missing_body:
        gaps.append(f"未填{'、'.join(missing_body)}，合身维度未参与")

    missing_length = [it for it in tops if it.length_cm is None]
    if len(tops) >= 3 and missing_length:
        gaps.append(f"有 {len(missing_length)} 件上装没量衣长，下摆错层未判")
    if len(tops) >= 2 and any(it.material is None for it in tops):
        gaps.append("有上装未填材质，材质对比未判")
    outer = candidate.placement.get("outer_layer")
    if outer is not None and outer.length_cm is not None and ctx.height_cm is None:
        gaps.append("未填身高，外套下摆比例未判")
    if ctx.feels_like is None:
        gaps.append("未填体感温度，温度带与暖度未判")
    return tuple(gaps[:MAX_GAPS])


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def explain(assessment: Assessment, ctx: Context) -> Explanation:
    """把一套已通过硬规则的组合翻译成结构化解释。纯函数、确定性。"""
    chosen = _select_lines(_positive_lines(assessment))
    lines = [
        _line(item.principle, item.rule_id, item.evidence)
        for item in chosen
    ]
    if len(lines) < 2:
        baseline = _baseline_line(assessment, chosen)
        if baseline is not None:
            lines.append(baseline)
    lines.sort(
        key=lambda line: (
            _AXIS_ORDER[PRINCIPLE_BY_ID[line.principle_id].axis],
            line.kind,
        )
    )
    principles = tuple(lines[:MAX_LINES])
    style = _style(assessment, ctx)
    caveats = _caveats(assessment, ctx)
    return Explanation(
        headline=_headline(principles, style, caveats, ctx, assessment.level),
        principles=principles,
        caveats=caveats,
        style=style,
        data_gaps=_data_gaps(assessment, ctx),
        version=VERSION,
    )


__all__ = [
    "LINE_BY_RULE",
    "LINE_SPECS",
    "MAX_CAVEATS",
    "MAX_LINES",
    "Caveat",
    "Explanation",
    "ExplanationLine",
    "StyleProfile",
    "explain",
]
