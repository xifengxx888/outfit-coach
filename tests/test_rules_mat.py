"""材质模块 R-MAT-01 的单测。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Status


def test_mat_01_rewards_stiff_outer_over_soft_inner() -> None:
    c = outfit(
        base=layer_item("base", material="棉"),
        outer=layer_item("outer", material="牛仔"),
    )
    hit = run_rule("R-MAT-01", c)
    assert hit.is_scored
    assert hit.value == 1.5


def test_mat_01_skips_when_both_layers_are_soft() -> None:
    c = outfit(
        base=layer_item("base", material="棉"),
        outer=layer_item("outer", material="针织"),
    )
    assert run_rule("R-MAT-01", c).status is Status.SKIP


def test_mat_01_skips_when_material_is_missing() -> None:
    c = outfit(
        base=layer_item("base", material=None),
        outer=layer_item("outer", material="牛仔"),
    )
    assert run_rule("R-MAT-01", c).status is Status.SKIP
