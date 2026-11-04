"""材质模块（MAT）——1 条规则。

课程口径：材质是"哑光/光泽、软/硬"的对比。外层挺括撑得起轮廓，
内层柔软贴着身体，这是叠穿质感的基础。反过来（软外套罩硬内搭）会显得邋遢。

- R-MAT-01 软：相邻层材质有对比（外层挺括/粗糙、内层平滑/柔软），+1.5
  `material` 缺失则跳过。材质是 VLM 最不可靠的字段（实测约 67%），
  所以这条规则大部分时候返回 SKIP——这是设计好的，不是失败。
"""

from __future__ import annotations

from .types import Candidate, Context, Kind, RuleHit, Status

SOFT = Kind.SOFT
PASS, SKIP = Status.PASS, Status.SKIP

TOP_SLOTS = ("base_top", "mid_layer", "outer_layer")

# 挺括 / 粗糙：能撑轮廓
STIFF_MATERIALS = frozenset({"牛仔", "皮革", "尼龙", "羊毛", "帆布", "防水涂层"})
# 平滑 / 柔软：贴身体
SOFT_MATERIALS = frozenset({"棉", "针织", "亚麻", "化纤", "缎面", "麂皮"})


def rule_mat_01(c: Candidate, ctx: Context, tol: float) -> RuleHit:
    # 任意相邻一对成立即可，不要求最外层与最内层同时满足
    tops = c.items_in(TOP_SLOTS)
    for inner, outer in zip(tops, tops[1:]):
        if not inner.material or not outer.material:
            continue
        if outer.material in STIFF_MATERIALS and inner.material in SOFT_MATERIALS:
            return RuleHit(
                "R-MAT-01", SOFT, PASS, 1.5,
                f"外层{outer.material}挺括、内层{inner.material}柔软，有材质对比",
            )
    return RuleHit("R-MAT-01", SOFT, SKIP)


RULES = (("R-MAT-01", rule_mat_01),)

__all__ = ["RULES", "SOFT_MATERIALS", "STIFF_MATERIALS"]
