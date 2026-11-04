"""登记表单测：规则总数、放宽白名单、求值入口，以及「每条规则至少两个用例」的覆盖检查。"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from factories import layer_item, outfit
from src.rules.registry import (
    HARD_RULES,
    RULE_NAMES,
    SOFT_RULES,
    evaluate_hard,
    evaluate_soft,
    rule_kind,
)
from src.rules.types import Context, Kind, Status

EXPECTED_RELAXABLE = frozenset(
    {"R-FRM-01", "R-FRM-02", "R-LYR-01", "R-SHO-01", "R-OCC-01"}
)
RULE_ID_PATTERN = re.compile(r"^R-[A-Z]{3}-\d{2}$")
TESTS_DIR = Path(__file__).parent


def test_registry_has_26_unique_rules() -> None:
    all_ids = [spec.rule_id for spec in (*HARD_RULES, *SOFT_RULES)]
    assert len(all_ids) == 26
    assert len(set(all_ids)) == 26
    assert set(all_ids) == set(RULE_NAMES)


def test_hard_and_soft_sets_do_not_overlap() -> None:
    hard = {spec.rule_id for spec in HARD_RULES}
    soft = {spec.rule_id for spec in SOFT_RULES}
    assert hard.isdisjoint(soft)
    assert len(hard) == 10


def test_only_degree_rules_are_relaxable() -> None:
    relaxable = {spec.rule_id for spec in HARD_RULES if spec.relaxable}
    assert relaxable == EXPECTED_RELAXABLE
    assert not any(spec.relaxable for spec in SOFT_RULES)


def test_rule_kind_matches_the_registry_split() -> None:
    for spec in HARD_RULES:
        assert rule_kind(spec.rule_id) is Kind.HARD
    for spec in SOFT_RULES:
        assert rule_kind(spec.rule_id) is Kind.SOFT


def test_evaluate_hard_ignores_tolerance_for_relationship_rules() -> None:
    # 主色数属于关系类，放宽到 2.0 也不能过
    c = outfit(
        base=layer_item("base", color_hex="#C0392B"),
        outer=layer_item("outer", color_hex="#1F6FEB"),
        bottom=layer_item("bottom", color_hex="#27AE60"),
        shoes=layer_item("shoes", color_hex="#F1C40F"),
    )
    strict = evaluate_hard(c, Context(), tol=0.0)
    relaxed = evaluate_hard(c, Context(), tol=2.0)
    assert strict["R-COL-01"].is_fail
    assert relaxed["R-COL-01"].is_fail


def test_evaluate_hard_passes_tolerance_to_degree_rules() -> None:
    c = outfit(
        base=layer_item("base", weight="thick"),
        outer=layer_item("outer", weight="medium"),
    )
    assert evaluate_hard(c, Context(), tol=1.0)["R-LYR-01"].is_fail
    assert evaluate_hard(c, Context(), tol=2.0)["R-LYR-01"].status is Status.PASS


def test_evaluate_soft_returns_one_hit_per_soft_rule() -> None:
    hits = evaluate_soft(outfit(), Context())
    assert len(hits) == len(SOFT_RULES)
    assert [hit.rule_id for hit in hits] == [spec.rule_id for spec in SOFT_RULES]


def _rule_ids_used_by_tests() -> dict[str, set[str]]:
    """扫测试源码：每个规则 id 出现在哪些测试函数里。"""
    used: dict[str, set[str]] = {rule_id: set() for rule_id in RULE_NAMES}
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if not node.name.startswith("test_"):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    if RULE_ID_PATTERN.match(sub.value):
                        used.setdefault(sub.value, set()).add(
                            f"{path.name}::{node.name}"
                        )
    return used


def test_every_rule_has_at_least_two_test_cases() -> None:
    used = _rule_ids_used_by_tests()
    assert set(used) == set(RULE_NAMES), "测试里出现了登记表之外的规则 id"
    thin = {
        rule_id: sorted(cases)
        for rule_id, cases in used.items()
        if len(cases) < 2
    }
    assert not thin, f"以下规则的单测不足 2 个用例：{thin}"
