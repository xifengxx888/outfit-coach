"""尺寸合身模块 2 条复合软规则的单测。

两组用例分别覆盖：合身加分、单维度扣分、短袖跳过、按维度取最差、
跨维度按件合并、同一件多槽去重、来源降权、下限截断与缺数据跳过。
"""

from __future__ import annotations

from factories import layer_item, make_item, outfit, run_rule
from src.rules.types import Context, Status


def _body() -> Context:
    """用户实测身材：肩 43 / 胸 91 / 臀 91 / 臂 53。"""
    return Context(shoulder_cm=43.0, chest_cm=91.0, hip_cm=91.0, arm_cm=53.0)


def _top(name: str = "测试单品", **overrides: object):
    return layer_item("base", name=name, **overrides)


# ---------------------------------------------------------------------------
# R-SIZ-01 上装合身
# ---------------------------------------------------------------------------


def test_siz_01_rewards_a_well_fitting_top() -> None:
    base = _top(shoulder_cm=44.0, chest_width_cm=49.0, sleeve_cm=56.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    assert hit.status is Status.PASS
    assert hit.value == 0.2
    assert (hit.reason or "").startswith("上装合身")
    assert "合适" in (hit.reason or "")


def test_siz_01_penalizes_narrow_shoulders() -> None:
    base = _top(shoulder_cm=39.0, chest_width_cm=49.0, sleeve_cm=56.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    assert hit.value == -1.0
    assert "肩线窄 4cm" in (hit.reason or "")


def test_siz_01_allows_dropped_shoulders_on_oversize() -> None:
    base = _top(fit="oversize", shoulder_cm=56.0, chest_width_cm=53.0, sleeve_cm=56.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    assert hit.value == 0.2
    assert "合适" in (hit.reason or "")


def test_siz_01_penalizes_a_tight_chest() -> None:
    base = _top(shoulder_cm=44.0, chest_width_cm=45.0, sleeve_cm=56.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    assert hit.value == -1.0
    assert "胸围松量 -1cm，偏紧" in (hit.reason or "")


def test_siz_01_skips_sleeve_for_short_sleeves() -> None:
    base = _top(shoulder_cm=44.0, chest_width_cm=49.0, sleeve_cm=20.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    assert hit.value == 0.2
    assert "袖" not in (hit.reason or "")


def test_siz_01_counts_each_dimension_once() -> None:
    base = _top(shoulder_cm=39.0, chest_width_cm=49.0, sleeve_cm=56.0)
    outer = layer_item(
        "outer", shoulder_cm=39.0, chest_width_cm=53.0, sleeve_cm=56.0
    )
    hit = run_rule("R-SIZ-01", outfit(base=base, outer=outer), _body())
    # 两件都窄肩，肩线维度只扣一次
    assert hit.value == -1.0


def test_siz_01_merges_problems_per_item_across_dimensions() -> None:
    base = _top(name="窄肩T恤", shoulder_cm=39.0, chest_width_cm=49.0, sleeve_cm=56.0)
    outer = layer_item("outer", name="紧胸夹克", chest_width_cm=46.0, sleeve_cm=56.0)
    hit = run_rule("R-SIZ-01", outfit(base=base, outer=outer), _body())
    reason = hit.reason or ""
    assert hit.value == -2.0
    assert reason.count("窄肩T恤") == 1
    assert reason.count("紧胸夹克") == 1
    assert "；" not in reason


def test_siz_01_evaluates_one_item_in_two_slots_once() -> None:
    # 同一件占了中层与外层：只按最外层（松量区间最宽）判一次
    item = layer_item("mid", fit="oversize", chest_width_cm=51.5)
    hit = run_rule("R-SIZ-01", outfit(mid=item, outer=item), _body())
    assert hit.value == -1.0
    assert "偏紧" in (hit.reason or "")


def test_siz_01_keeps_penalties_as_pass_with_negative_value() -> None:
    base = _top(shoulder_cm=39.0)
    hit = run_rule("R-SIZ-01", outfit(base=base), _body())
    # 写成 FAIL 会让理由与 thumbs_down 一起消失
    assert hit.status is Status.PASS
    assert hit.value < 0


def test_siz_01_skips_when_body_or_garment_data_is_missing() -> None:
    measured = _top(shoulder_cm=44.0, chest_width_cm=49.0, sleeve_cm=56.0)
    assert run_rule("R-SIZ-01", outfit(base=measured)).status is Status.SKIP
    hit = run_rule("R-SIZ-01", outfit(base=_top()), _body())
    assert hit.status is Status.SKIP
    assert hit.reason is None


def test_siz_01_halves_scores_and_marks_estimated_sources() -> None:
    narrow = _top(shoulder_cm=39.0, chest_width_cm=49.0, sleeve_cm=56.0)
    estimated = Context(
        shoulder_cm=43.0,
        chest_cm=91.0,
        arm_cm=53.0,
        body_sources={"shoulder_width": "estimated", "chest": "estimated",
                      "arm_length": "estimated"},
    )
    hit = run_rule("R-SIZ-01", outfit(base=narrow), estimated)
    assert hit.value == -0.5
    assert "估算" in (hit.reason or "")

    fitting = _top(shoulder_cm=44.0, chest_width_cm=49.0, sleeve_cm=56.0)
    bonus = run_rule("R-SIZ-01", outfit(base=fitting), estimated)
    assert bonus.value == 0.1
    assert "估算" in (bonus.reason or "")


def test_siz_01_clamps_severe_misfit_to_the_floor() -> None:
    def bad(slot: str):
        return layer_item(
            slot, shoulder_cm=38.0, chest_width_cm=40.0, sleeve_cm=63.0
        )

    c = outfit(base=bad("base"), mid=bad("mid"), outer=bad("outer"))
    hit = run_rule("R-SIZ-01", c, _body())
    assert hit.value == -2.5


# ---------------------------------------------------------------------------
# R-SIZ-02 下装合身
# ---------------------------------------------------------------------------


def test_siz_02_rewards_a_good_hip_ease() -> None:
    bottom = layer_item("bottom", hip_cm=47.0)
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), _body())
    assert hit.status is Status.PASS
    assert hit.value == 0.2
    assert hit.reason == "下装合身：臀围松量 3cm，合适"


def test_siz_02_marks_a_snug_fit() -> None:
    bottom = layer_item("bottom", hip_cm=45.5)
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), _body())
    assert hit.value == 0.1
    assert "贴体" in (hit.reason or "")


def test_siz_02_penalizes_a_tight_hip() -> None:
    bottom = layer_item("bottom", hip_cm=44.0)
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), _body())
    assert hit.value == -1.0
    assert "坐下会绷" in (hit.reason or "")


def test_siz_02_penalizes_a_loose_hip() -> None:
    bottom = layer_item("bottom", hip_cm=52.0)
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), _body())
    assert hit.value == -0.3
    assert "偏肥" in (hit.reason or "")


def test_siz_02_skips_without_hip_data() -> None:
    bottom = layer_item("bottom", hip_cm=47.0)
    assert run_rule("R-SIZ-02", outfit(bottom=bottom)).status is Status.SKIP
    assert run_rule("R-SIZ-02", outfit(bottom=layer_item("bottom")), _body()).status is Status.SKIP


def test_siz_02_judges_a_jumpsuit_alongside_the_top_rule() -> None:
    jumpsuit = make_item(
        id=9,
        name="连体工装",
        category="连体装",
        layers=("inner", "bottom"),
        shoulder_cm=44.0,
        chest_width_cm=47.0,
        sleeve_cm=56.0,
        hip_cm=46.0,
    )
    c = outfit(base=jumpsuit, bottom=jumpsuit)
    top = run_rule("R-SIZ-01", c, _body())
    bottom = run_rule("R-SIZ-02", c, _body())
    assert top.value == 0.2
    assert bottom.value == 0.1
    assert (top.reason or "").startswith("上装合身")
    assert (bottom.reason or "").startswith("下装合身")


def test_siz_02_halves_bonus_for_estimated_hip() -> None:
    bottom = layer_item("bottom", hip_cm=47.0)
    ctx = Context(hip_cm=91.0, body_sources={"hip": "estimated"})
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), ctx)
    assert hit.value == 0.1
    assert "估算" in (hit.reason or "")


def test_siz_02_never_goes_below_the_floor() -> None:
    bottom = layer_item("bottom", hip_cm=20.0)
    hit = run_rule("R-SIZ-02", outfit(bottom=bottom), _body())
    assert hit.value == -1.0
