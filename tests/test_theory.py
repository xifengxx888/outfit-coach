"""搭配原理表：覆盖、元数据、文档同源与来源规范。"""

from __future__ import annotations

import re
from pathlib import Path

from src.rules import RULE_NAMES
from src.rules.theory import (
    AXIS_ORDER,
    DISPLAY_ORDER,
    GRADE_LABELS,
    PRINCIPLE_BY_ID,
    PRINCIPLES,
    PRINCIPLES_BY_RULE,
    STATUS_LABELS,
    UNSUPPORTED,
)

DOC = Path(__file__).resolve().parents[1] / "docs" / "11-搭配理论库.md"


def test_all_26_rules_are_mapped() -> None:
    assert len(RULE_NAMES) == 26
    assert set(PRINCIPLES_BY_RULE) == set(RULE_NAMES)
    for rule_id, principles in PRINCIPLES_BY_RULE.items():
        assert principles, f"{rule_id} 没有对应原理"


def test_principle_count_and_ids() -> None:
    assert len(PRINCIPLES) == 18
    ids = [p.id for p in PRINCIPLES]
    assert len(ids) == len(set(ids))
    assert all(re.match(r"^P-[A-Z]{3}-\d{2}$", pid) for pid in ids)
    assert set(PRINCIPLE_BY_ID) == set(ids)


def test_principle_metadata_is_valid() -> None:
    assert set(GRADE_LABELS) == {"A", "B", "C", "D"}
    assert set(STATUS_LABELS) == {
        "active",
        "conditional",
        "baseline",
        "boundary",
        "dormant",
    }
    for principle in PRINCIPLES:
        assert principle.grade in GRADE_LABELS
        assert principle.grade_label == GRADE_LABELS[principle.grade]
        assert principle.status in STATUS_LABELS
        assert principle.axis in AXIS_ORDER


def test_principle_text_is_not_empty() -> None:
    for principle in PRINCIPLES:
        for field in ("title", "claim", "why", "how_to_judge", "source"):
            assert getattr(principle, field).strip(), f"{principle.id}.{field} 为空"


def test_no_unknown_rule_ids() -> None:
    for principle in PRINCIPLES:
        for rule_id in principle.rule_ids:
            assert rule_id in RULE_NAMES, f"{principle.id} 引用了未知规则 {rule_id}"


def test_source_url_must_be_https() -> None:
    for principle in PRINCIPLES:
        if principle.source_url is not None:
            assert principle.source_url.startswith("https://")


def test_every_principle_id_appears_in_docs() -> None:
    text = DOC.read_text(encoding="utf-8")
    missing = [p.id for p in PRINCIPLES if p.id not in text]
    assert not missing, f"docs/11 缺少原理：{missing}"


def test_docs_lists_every_rule_id() -> None:
    text = DOC.read_text(encoding="utf-8")
    missing = [rule_id for rule_id in RULE_NAMES if rule_id not in text]
    assert not missing, f"docs/11 缺少规则：{missing}"


def test_display_order_follows_axis_order() -> None:
    assert len(DISPLAY_ORDER) == len(PRINCIPLES)
    seen_axes = [PRINCIPLE_BY_ID[pid].axis for pid in DISPLAY_ORDER]
    assert seen_axes == sorted(seen_axes, key=AXIS_ORDER.index)


def test_unsupported_topics_are_complete() -> None:
    assert len(UNSUPPORTED) >= 8
    for topic in UNSUPPORTED:
        assert topic.topic.strip()
        assert topic.why.strip()
        assert topic.needed.strip()


def test_known_dormant_principles() -> None:
    dormant = {p.id for p in PRINCIPLES if p.status == "dormant"}
    assert dormant == {"P-VIS-02", "P-LAY-03", "P-TEX-01", "P-PAT-01"}
