"""解释层：证据来源、选择顺序、caveat 分流与确定性。"""

from __future__ import annotations

import time

import pytest

from src.rules.explain import (
    MAX_CAVEATS,
    MAX_LINES,
    StyleProfile,
    explain,
)
from src.rules.solver import Assessment, assess
from src.rules.theory import AXIS_ORDER, PRINCIPLE_BY_ID
from src.rules.types import Context
from tests.factories import make_item, outfit

BODY = Context(
    occasion="日常",
    feels_like=16,
    height_cm=165,
    shoulder_cm=40,
    chest_cm=90,
    hip_cm=90,
    arm_cm=58,
)


def rich_outfit():
    """三层、同色系深浅、上窄下宽、鞋色呼应、合身；同时触发两条 dormant 规则。"""
    base = make_item(
        id=1,
        name="深灰内搭",
        formality=2,
        color_hex="#303030",
        fit="regular",
        weight="medium",
        material="棉",
        collar="圆领",
        length_cm=60,
        shoulder_cm=41,
        chest_width_cm=47,
        sleeve_cm=60,
    )
    mid = make_item(
        id=4,
        name="中灰卫衣",
        category="卫衣",
        layers=("mid",),
        formality=2,
        color_hex="#808080",
        fit="regular",
        weight="medium",
        material="棉",
        collar="连帽",
        length_cm=65,
    )
    outer = make_item(
        id=5,
        name="黑色夹克",
        category="夹克",
        layers=("outer",),
        formality=2,
        color_hex="#303030",
        fit="slim",
        weight="medium",
        material="牛仔",
        collar="翻领",
        pattern="bold",
        length_cm=70,
    )
    bottom = make_item(
        id=2,
        name="中灰运动裤",
        category="裤子",
        layers=("bottom",),
        formality=2,
        color_hex="#808080",
        fit="oversize",
        weight="medium",
        material="棉",
        hip_cm=46,
    )
    shoes = make_item(
        id=3,
        name="黑色鞋",
        category="鞋",
        layers=("shoes",),
        formality=2,
        color_hex="#303030",
        material="皮革",
    )
    return outfit(base, mid, outer, bottom, shoes)


def grey_black_outfit():
    base = make_item(
        id=1,
        name="浅灰卫衣",
        category="卫衣",
        formality=2,
        color_hex="#97948F",
        weight="medium",
        material="棉",
        collar="圆领",
        length_cm=60,
    )
    outer = make_item(
        id=5,
        name="黑色夹克",
        category="夹克",
        layers=("outer",),
        formality=2,
        color_hex="#121212",
        weight="medium",
        material="棉",
        collar="连帽",
        length_cm=66,
    )
    bottom = make_item(
        id=2,
        name="中灰裤子",
        category="裤子",
        layers=("bottom",),
        formality=2,
        color_hex="#808080",
        weight="medium",
        material="棉",
    )
    shoes = make_item(
        id=3,
        name="黑色鞋",
        category="鞋",
        layers=("shoes",),
        formality=2,
        color_hex="#121212",
        material="皮革",
    )
    return outfit(base, outer=outer, bottom=bottom, shoes=shoes)


def assessed(candidate, ctx: Context = BODY) -> Assessment:
    result = assess(candidate, ctx)
    assert result is not None, "测试组合必须至少能通过放宽后的硬规则"
    return result


def test_explain_is_deterministic() -> None:
    first = assessed(rich_outfit())
    second = assessed(rich_outfit())
    assert explain(first, BODY) == explain(first, BODY)
    assert explain(first, BODY) == explain(second, BODY)


def test_principle_display_order() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    axes = [PRINCIPLE_BY_ID[line.principle_id].axis for line in explanation.principles]
    assert axes == sorted(axes, key=AXIS_ORDER.index)
    assert axes[:3] == ["silhouette", "color", "color"]


def test_max_five_principles_and_two_per_axis() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    assert len(explanation.principles) == MAX_LINES
    axes = [PRINCIPLE_BY_ID[line.principle_id].axis for line in explanation.principles]
    assert all(axes.count(axis) <= 2 for axis in axes)
    assert "fit" in axes, "有合身证据时必须给合身行留位置"


def test_negative_rule_never_becomes_positive_principle() -> None:
    candidate = rich_outfit()
    bottom = candidate.placement["bottom"]
    candidate = outfit(
        candidate.placement["base_top"],
        candidate.placement["mid_layer"],
        candidate.placement["outer_layer"],
        make_item(
            id=bottom.id,
            name=bottom.name,
            category=bottom.category,
            layers=bottom.layers,
            formality=bottom.formality,
            color_hex=bottom.color_hex,
            fit=bottom.fit,
            weight=bottom.weight,
            material=bottom.material,
            hip_cm=60,
        ),
        candidate.placement["shoes"],
    )
    assessment = assessed(candidate)
    explanation = explain(assessment, BODY)
    hits = {hit.rule_id: hit for hit in assessment.soft_hits}
    assert hits["R-SIZ-02"].value < 0
    assert all(line.rule_id != "R-SIZ-02" for line in explanation.principles)
    caveat = next(c for c in explanation.caveats if c.rule_id == "R-SIZ-02")
    assert caveat.code == "negative_soft"
    assert "偏肥" in caveat.text


def test_relaxed_rules_become_caveats() -> None:
    ctx = Context(occasion="日常", feels_like=22)
    base = make_item(id=1, formality=2, color_hex="#808080")
    bottom = make_item(
        id=2,
        name="灰裤子",
        category="裤子",
        layers=("bottom",),
        formality=2,
        color_hex="#808080",
    )
    shoes = make_item(
        id=3,
        name="正装鞋",
        category="鞋",
        layers=("shoes",),
        formality=4,
        color_hex="#808080",
    )
    assessment = assessed(outfit(base, bottom=bottom, shoes=shoes), ctx)
    assert assessment.level == 2
    assert assessment.relaxed_rules == ("R-SHO-01",)
    explanation = explain(assessment, ctx)
    assert explanation.caveats[0].code == "relaxed"
    assert "R-SHO-01" in explanation.caveats[0].text
    assert "放宽 2 档" in explanation.headline


def test_occ_skip_becomes_context_caveat() -> None:
    ctx = Context(occasion="见人", feels_like=22)
    base = make_item(id=1, formality=2, color_hex="#121212")
    bottom = make_item(
        id=2,
        name="灰裤子",
        category="裤子",
        layers=("bottom",),
        formality=2,
        color_hex="#808080",
    )
    shoes = make_item(
        id=3,
        name="黑鞋",
        category="鞋",
        layers=("shoes",),
        formality=2,
        color_hex="#121212",
    )
    assessment = assessed(outfit(base, bottom=bottom, shoes=shoes), ctx)
    hits = {hit.rule_id: hit for hit in assessment.soft_hits}
    assert hits["R-OCC-02"].reason is None
    assert hits["R-OCC-03"].reason is None
    explanation = explain(assessment, ctx)
    context = [c for c in explanation.caveats if c.code == "context"]
    assert {c.rule_id for c in context} == {"R-OCC-02", "R-OCC-03"}
    assert "正式度与场合有偏差" in explanation.headline
    assert "暖度与体感有偏差" in explanation.headline


def test_style_not_scored_and_marked_inferred() -> None:
    assessment = assessed(rich_outfit())
    before = assessment.score
    explanation = explain(assessment, BODY)
    assert assessment.score == before
    assert isinstance(explanation.style, StyleProfile)
    assert explanation.style.inferred is True
    assert "不参与评分" in explanation.style.caveat
    assert explanation.style.formality_band == "日常休闲"


def test_no_empty_filler() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    for line in explanation.principles:
        assert line.evidence.strip()
        assert "数据不足" not in line.evidence
        assert "暂无" not in line.evidence
        assert line.source.strip()
        assert line.grade_label.strip()
    assert "暂无" not in explanation.headline


def test_same_hue_and_neutral_anchor() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    ids = {line.principle_id for line in explanation.principles}
    assert {"P-COL-02", "P-COL-03"} <= ids
    same_hue = next(l for l in explanation.principles if l.principle_id == "P-COL-02")
    neutral = next(l for l in explanation.principles if l.principle_id == "P-COL-03")
    assert "ΔE00" in same_hue.evidence
    assert "中性色" in neutral.evidence


def test_silhouette_and_fit() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    ids = {line.principle_id for line in explanation.principles}
    assert "P-VIS-01" in ids
    assert {"P-FIT-01", "P-FIT-02"} <= ids
    assert explanation.style.silhouette == "上窄下宽"
    assert "上装修身 / 下装宽松" in explanation.style.basis


def test_missing_body_data() -> None:
    ctx = Context(occasion="日常", feels_like=16, height_cm=165)
    explanation = explain(assessed(rich_outfit(), ctx), ctx)
    assert any("合身维度未参与" in gap for gap in explanation.data_gaps)
    assert all(not line.principle_id.startswith("P-FIT-") for line in explanation.principles)


def test_dormant_principles_never_become_positive_lines() -> None:
    assessment = assessed(rich_outfit())
    hits = {hit.rule_id: hit for hit in assessment.soft_hits}
    assert hits["R-MAT-01"].value > 0
    assert hits["R-PAT-02"].value > 0
    explanation = explain(assessment, BODY)
    ids = {line.principle_id for line in explanation.principles}
    assert "P-TEX-01" not in ids
    assert "P-PAT-01" not in ids


def test_baseline_line_when_only_one_positive() -> None:
    ctx = Context(occasion="见人", feels_like=22)
    base = make_item(id=1, formality=2, color_hex="#808080")
    bottom = make_item(
        id=2,
        name="灰裤子",
        category="裤子",
        layers=("bottom",),
        formality=2,
        color_hex="#808080",
    )
    shoes = make_item(
        id=3,
        name="蓝鞋",
        category="鞋",
        layers=("shoes",),
        formality=2,
        color_hex="#0000FF",
    )
    assessment = assessed(outfit(base, bottom=bottom, shoes=shoes), ctx)
    explanation = explain(assessment, ctx)
    baseline = [line for line in explanation.principles if line.kind == "baseline"]
    assert len(baseline) == 1
    assert baseline[0].principle_id == "P-SOC-01"
    assert baseline[0].rule_id == "R-SHO-01"
    assert "没有抢调" in baseline[0].evidence


def test_real_outfit_grey_black() -> None:
    explanation = explain(assessed(grey_black_outfit()), BODY)
    assert 4 <= len(explanation.principles) <= MAX_LINES
    assert explanation.headline.startswith("16°C 日常：")
    assert "同色系深浅" in explanation.headline
    assert "中性色打底" in explanation.headline
    assert explanation.caveats == ()


def test_real_outfit_slim_oversize() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    assert len(explanation.principles) == MAX_LINES
    assert explanation.headline.startswith("16°C 日常：")
    assert "上窄下宽" in explanation.headline
    assert "偏极简" in explanation.style.label
    assert explanation.caveats == ()


def test_every_principle_traces_to_a_positive_soft_hit() -> None:
    for candidate in (rich_outfit(), grey_black_outfit()):
        assessment = assessed(candidate)
        explanation = explain(assessment, BODY)
        hits = {hit.rule_id: hit for hit in assessment.soft_hits}
        for line in explanation.principles:
            if line.kind == "baseline":
                continue
            assert hits[line.rule_id].is_scored
            assert hits[line.rule_id].value > 0


def test_caveat_budget() -> None:
    explanation = explain(assessed(rich_outfit()), BODY)
    assert len(explanation.caveats) <= MAX_CAVEATS
    assert len(explanation.data_gaps) <= 2


def test_explain_perf_budget() -> None:
    assessment = assessed(rich_outfit())
    start = time.perf_counter()
    for _ in range(100):
        explain(assessment, BODY)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"100 次 explain 耗时 {elapsed:.3f}s"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
