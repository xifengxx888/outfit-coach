"""鞋与配饰模块 3 条规则的单测。"""

from __future__ import annotations

from factories import layer_item, outfit, run_rule
from src.rules.types import Context, Status


def test_sho_01_fails_when_shoe_formality_is_far_off() -> None:
    c = outfit(shoes=layer_item("shoes", formality=1))
    hit = run_rule("R-SHO-01", c)
    assert hit.is_fail
    assert "差 2.0" in (hit.reason or "")


def test_sho_01_passes_at_gap_of_one() -> None:
    c = outfit(shoes=layer_item("shoes", formality=2))
    assert run_rule("R-SHO-01", c).status is Status.PASS


def test_sho_02_rewards_an_echo_between_shoe_and_top() -> None:
    hit = run_rule("R-SHO-02", outfit())
    assert hit.is_scored
    assert hit.value == 1.5


def test_sho_02_skips_when_shoe_colour_is_unrelated() -> None:
    c = outfit(shoes=layer_item("shoes", color_hex="#C0392B"))
    assert run_rule("R-SHO-02", c).status is Status.SKIP


def test_sho_03_penalises_suede_in_the_rain() -> None:
    c = outfit(shoes=layer_item("shoes", material="麂皮"))
    hit = run_rule("R-SHO-03", c, Context(is_rainy=True))
    assert hit.is_scored
    assert hit.value == -1.5


def test_sho_03_rewards_leather_in_the_rain() -> None:
    c = outfit(shoes=layer_item("shoes", material="皮革"))
    hit = run_rule("R-SHO-03", c, Context(is_rainy=True))
    assert hit.is_scored
    assert hit.value == 1.0


def test_sho_03_skips_when_not_raining() -> None:
    c = outfit(shoes=layer_item("shoes", material="麂皮"))
    assert run_rule("R-SHO-03", c, Context(is_rainy=False)).status is Status.SKIP
