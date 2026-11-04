"""搭配原理表：解释层的静态知识库。

这份数据是 `docs/11-搭配理论库.md` 的代码化版本。它只做三件事：

1. 给每条原理一个稳定的 `P-*` ID 与元数据（标题、主张、为什么、怎么判断、依据等级、来源）；
2. 把原理映射到真实执行的规则 ID，保证解释不脱离代码；
3. 标记每条原理在当前衣柜数据下的状态，避免把算不出来的理论硬凑进解释。

约束：本模块不 import `src/db/` 或 `src/api/`，不读文件，不做判断。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .registry import RULE_NAMES

GRADE_LABELS = {
    "A": "可测量科学",
    "B": "实验与标准",
    "C": "造型经验",
    "D": "数据不足",
}

STATUS_LABELS = {
    "active": "生效",
    "conditional": "条件生效",
    "baseline": "结构底线",
    "boundary": "边界",
    "dormant": "当前数据不足",
}

AXIS_ORDER = (
    "silhouette",
    "color",
    "fit",
    "layer",
    "social",
    "texture",
    "pattern",
)

AXIS_LABELS = {
    "silhouette": "视觉平衡与比例",
    "color": "色彩关系",
    "fit": "合身与结构",
    "layer": "层次结构",
    "social": "社会语境",
    "texture": "材质",
    "pattern": "图案",
}

_STATUSES = frozenset(STATUS_LABELS)
_GRADES = frozenset(GRADE_LABELS)
_ID_RE = re.compile(r"^P-[A-Z]{3}-\d{2}$")


@dataclass(frozen=True)
class Principle:
    id: str
    title: str
    claim: str
    why: str
    how_to_judge: str
    grade: str
    grade_label: str
    source: str
    source_url: str | None
    rule_ids: tuple[str, ...]
    axis: str
    status: str


@dataclass(frozen=True)
class UnsupportedTopic:
    topic: str
    why: str
    needed: str


def _p(
    *,
    id: str,
    title: str,
    claim: str,
    why: str,
    how_to_judge: str,
    grade: str,
    source: str,
    rule_ids: tuple[str, ...],
    axis: str,
    status: str,
    source_url: str | None = None,
) -> Principle:
    return Principle(
        id=id,
        title=title,
        claim=claim,
        why=why,
        how_to_judge=how_to_judge,
        grade=grade,
        grade_label=GRADE_LABELS[grade],
        source=source,
        source_url=source_url,
        rule_ids=rule_ids,
        axis=axis,
        status=status,
    )


PRINCIPLES: tuple[Principle, ...] = (
    # 视觉平衡与比例
    _p(
        id="P-VIS-01",
        title="轮廓靠一宽一窄成立",
        claim="上下装至少要有一侧收、一侧放；上下同宽会合并成一个方块，上下同紧会显得局促。",
        why="人眼先读外轮廓，再读内部细节。肩线到下摆、腰头到裤脚是两条独立的体量信号；两侧体量相同，边界消失，身体被读成一个整体块。只有宽窄差足够大，才会出现明确的横向分割线。",
        how_to_judge="先看肩到下摆的外轮廓，再看裤脚宽度；只允许一侧松。上下版型差 2 级（修身↔宽松）才成立。",
        grade="C",
        source="造型教学中的 volume balance 原则（本项目以 FIT_IDX 离散化）",
        rule_ids=("R-PRP-01", "R-PRP-02", "R-PRP-03"),
        axis="silhouette",
        status="active",
    ),
    _p(
        id="P-VIS-02",
        title="外套下摆超过身高 55% 会压低重心",
        claim="身高较矮时，外套下摆超过身高 55% 会压低视觉重心，腿看起来更短。",
        why="外套下摆是全身最明确的一条水平线，眼睛会把它当成躯干与腿的分界。下摆越低，腿的可见长度越短；对小个子，这条线的影响大于颜色和图案。",
        how_to_judge="身高 <170cm 时，量外套后领中点到下摆；超过 0.55 × 身高就要警惕。165cm 对应 90.75cm。",
        grade="C",
        source="比例造型经验（55% 为本项目操作化阈值）",
        rule_ids=("R-PRP-04",),
        axis="silhouette",
        status="dormant",
    ),
    # 色彩关系
    _p(
        id="P-COL-01",
        title="相邻色差低于 ΔE00 10 会糊成一片",
        claim="相邻两层颜色不同但色差太小，会看起来像同一块布洗旧了，而不是有意的层次。",
        why="人眼对色差的分辨有下限。CIEDE2000 把色差归一化到 1 左右为刚可察觉，10 左右是明确可辨。低于这个量级、又属于不同色相家族时，既没有同色系的统一感，也没有对比色的分离感，只剩脏。",
        how_to_judge="看相邻层的 HEX 是否同色系；不同色系时，色差要明显到眯眼也能分出两块。代码阈值是 ΔE00 < 10 扣分。",
        grade="A",
        source="Sharma et al., The CIEDE2000 Color-Difference Formula, 2005",
        source_url="https://doi.org/10.1002/col.20070",
        rule_ids=("R-COL-02",),
        axis="color",
        status="conditional",
    ),
    _p(
        id="P-COL-02",
        title="同色系用明度差分层",
        claim="同一色相家族内拉开明度或色差，既保留统一感，又读得出层次。",
        why="同色系不增加主色数量，视觉预算不被占用；明度差提供边界，让相邻层不粘在一起。相比换一个色相，同色系更难出错，也更容易重复。",
        how_to_judge="眯眼看整体，能分出深浅块就成立；分不出就是糊成一片。代码阈值是同色系且 ΔE00 ≥ 10 加分。",
        grade="A",
        source="Sharma et al., 2005；Itten 色彩对比理论",
        source_url="https://doi.org/10.1002/col.20070",
        rule_ids=("R-COL-03",),
        axis="color",
        status="active",
    ),
    _p(
        id="P-COL-03",
        title="中性色是视觉锚点",
        claim="整套里至少有一件中性色（黑、白、灰、藏青、卡其等），整体更稳；彩色越多，越需要中性色兜底。",
        why="中性色饱和度低、不争抢注意力，给其他颜色提供参照。没有中性色时，多个彩色会同时争夺主色位置，视觉上没有落点。",
        how_to_judge="先找整套里最不抢眼的那一件；如果它是低饱和、黑、白、藏青或卡其，就有了锚点。",
        grade="B",
        source="Itten 色彩对比；Albers, Interaction of Color",
        rule_ids=("R-COL-06",),
        axis="color",
        status="active",
    ),
    _p(
        id="P-COL-04",
        title="主色数量与饱和度是视觉预算",
        claim="全身主色不超过 3 个；饱和度总量过高时，颜色会互相抢，失去主次。",
        why="把颜色当成有限的注意力预算。每多一个高饱和主色，眼睛就多一个竞争焦点；超过 3 个后，观众记不住这套的主色是什么。",
        how_to_judge="数非中性、饱和度 ≥15 的色相家族，不超过 3 个；再看全身饱和度合计，超过 200 就会吵。不声称 60-30-10 的精确面积比例。",
        grade="B",
        source="男装配色教学的三色上限 / 2+1 结构；Itten 色彩面积与强度",
        rule_ids=("R-COL-01", "R-COL-05"),
        axis="color",
        status="conditional",
    ),
    _p(
        id="P-COL-05",
        title="高饱和冷 + 高饱和暖并置会互相抢",
        claim="两件高饱和单品一冷一暖并置，会形成强烈冲突，除非这是刻意造型。",
        why="高饱和本身已经占据注意力；冷暖对立又增加一层张力。两者同时出现时，眼睛找不到统一色温，整体会显得吵。",
        how_to_judge="只看饱和度 ≥60 的单品；如果同时出现明显偏冷与明显偏暖的两件，就要问这是不是有意的撞色。",
        grade="B",
        source="Itten 七种色彩对比中的冷暖对比（60 为本项目阈值）",
        rule_ids=("R-COL-04",),
        axis="color",
        status="boundary",
    ),
    _p(
        id="P-COL-06",
        title="鞋与上身同色系形成上下呼应",
        claim="鞋的颜色与内搭、中层、外套或配饰同属一个色相家族，整套会形成上下呼应。",
        why="鞋在全身最底部，是视线的收尾。它与上身同色系时，颜色从上半身落到脚上，形成闭环；完全孤立的鞋色会把身体切成两段。",
        how_to_judge="遮住鞋以外的部分，只看鞋色；再放开，看它是否能在上半身找到同色系回应。代码要求同色系且 ΔE00 < 25。",
        grade="B",
        source="Gestalt 相似性；鞋履造型中的 shoe color echo",
        rule_ids=("R-SHO-02",),
        axis="color",
        status="active",
    ),
    # 合身与结构
    _p(
        id="P-FIT-01",
        title="上装合身看肩线、胸围松量、袖长",
        claim="上装是否合身，先看肩线落点，再看胸围松量，最后看袖长；三项里最差的一项决定整体判断。",
        why="肩线是上装的骨架，落点错了整件衣服的受力线就错了；胸围松量决定能否活动与是否有垂坠；袖长影响手臂比例。三项分开判断，才能指出哪里不合，而不是笼统说不合身。",
        how_to_judge="肩线落在肩点附近（偏差 ≤2.5cm），胸围能塞进两指到一拳，袖长到腕骨附近；一次只看一个维度。",
        grade="B",
        source="Aldrich, Metric Pattern Cutting；Armstrong, Patternmaking for Fashion Design",
        rule_ids=("R-SIZ-01",),
        axis="fit",
        status="active",
    ),
    _p(
        id="P-FIT-02",
        title="下装臀围松量兼顾坐姿与垂坠",
        claim="裤子的臀围松量要够坐、又不能大到失去垂坠；松量落在合适区间才算合身。",
        why="臀围是裤子活动量的核心。过紧坐下会绷，过松会在胯部堆布，破坏裤线。它和腰围不同，受低腰与弹力腰头影响小，更适合作为可计算指标。",
        how_to_judge="量裤臀围（平铺 ×2）减身体臀围；2–10cm 是合适区间，小于 0 会绷，大于 10 会堆布。",
        grade="B",
        source="Aldrich / Armstrong 的裤装松量章节",
        rule_ids=("R-SIZ-02",),
        axis="fit",
        status="active",
    ),
    # 层次结构
    _p(
        id="P-LAY-01",
        title="叠穿厚度由内到外不减",
        claim="内层薄、外层厚是默认结构；内厚外薄会显得臃肿，也不符合穿脱与热舒适逻辑。",
        why="厚度顺序同时是版型顺序与热舒适顺序。内层厚会在肩、腋下堆积，外层再薄也压不住；反过来，内薄外厚能提供可调节的空气层。",
        how_to_judge="从内到外摸厚度，应该越来越厚或持平；出现内厚外薄一次，就要问是不是外套选薄了。",
        grade="B",
        source="服装松量与叠穿结构常识；项目 R-OCC-01/03 厚度口径",
        rule_ids=("R-LYR-01",),
        axis="layer",
        status="baseline",
    ),
    _p(
        id="P-LAY-02",
        title="三层长度差 ≥5cm，层次才读得出来",
        claim="三层上装的下摆要逐层错开，相邻长度差至少 5cm；下摆齐平会把三层合并成一条线。",
        why="下摆是层次最直接的边界。差太小，眼睛读不出里面还有一层；差足够大，才会出现明确的阶梯。5cm 是项目内可操作的下限，不是绝对美学标准。",
        how_to_judge="看每层下摆的落点，相邻两层至少差一个指节到两指（约 5cm）；全齐平就只剩一条线。",
        grade="B",
        source="ELLE UK 比例与下摆错层指南；Gestalt 组织原则",
        rule_ids=("R-LYR-02",),
        axis="layer",
        status="active",
    ),
    _p(
        id="P-LAY-03",
        title="重复领型会合并成一个视觉块",
        claim="两层上装如果都是高领或都是连帽，领口会合并成一个视觉块，层次消失。",
        why="Gestalt 相似性会把形状、位置接近的元素归为一组。两个同形领口叠在一起，观者读到的不是两层，而是一个更厚的领子。",
        how_to_judge="只看领口；两层都是高领或都是连帽时，问自己能不能一眼数出两层领子。",
        grade="B",
        source="Gestalt 相似性原理（惩罚阈值由本项目设定）",
        rule_ids=("R-LYR-03",),
        axis="layer",
        status="dormant",
    ),
    # 社会语境
    _p(
        id="P-SOC-01",
        title="正式度要在全身连续",
        claim="正式度是一条连续谱，不是单件标签。相邻层差不超过 1 档，全身极差不超过 2 档；鞋也要跟全身同调。",
        why="人读到的是整套的场合信号，不是每件衣服的标签。上半身正装、下半身运动，或者鞋突然跳出两个档位，会让整套的语境断裂。连续性比单件精确更重要。",
        how_to_judge="把每件按 1–5 排一遍；相邻两件不超过 1 档，最高与最低不超过 2 档，鞋不要单独跳出。",
        grade="B",
        source="Business formal / Business casual / Smart casual / Casual 的通行定义",
        source_url="https://en.wikipedia.org/wiki/Business_casual",
        rule_ids=("R-FRM-01", "R-FRM-02", "R-SHO-01"),
        axis="social",
        status="baseline",
    ),
    _p(
        id="P-SOC-02",
        title="场合决定正式度目标区间",
        claim="日常与旅游的目标正式度是 2.0–3.0；见人是 3.5–4.5。整套均值落在区间内，场合才匹配。",
        why="同一套衣服在不同场合的对错不同。场合不是风格标签，而是一个可计算的正式度目标区间；先定目标，再谈单品。",
        how_to_judge="先问今天是什么场合，再把上装、下装、鞋的正式度取平均；日常 2–3，见人 3.5–4.5。",
        grade="B",
        source="着装规范通行定义（区间由本项目设定）",
        source_url="https://en.wikipedia.org/wiki/Business_casual",
        rule_ids=("R-OCC-02",),
        axis="social",
        status="active",
    ),
    _p(
        id="P-SOC-03",
        title="穿多少由体感温度决定；雨天材质优先",
        claim="层数与厚度要跟体感温度匹配；降水时鞋的材质优先选皮革、橡胶、防水涂层，避开麂皮、帆布、缎面。",
        why="体感温度包含风速与湿度，比气温更接近身体实际感受。穿多穿少是热舒适问题，不是审美问题；雨天则是功能问题，湿鞋会直接破坏整套体验。",
        how_to_judge="先看体感温度带：≥26°C 只内层，18–26°C 单层或薄外套，10–18°C 需中层或外套，<10°C 三层。下雨再看鞋材质。",
        grade="B",
        source="Open-Meteo Apparent Temperature 文档；项目温度带实测",
        source_url="https://open-meteo.com/en/docs",
        rule_ids=("R-OCC-01", "R-OCC-03", "R-SHO-03"),
        axis="social",
        status="active",
    ),
    # 材质
    _p(
        id="P-TEX-01",
        title="外层挺括、内层柔软，材质对比撑轮廓",
        claim="外层用挺括材质，内层用柔软材质，轮廓更清楚；内外都软会塌，内外都硬会僵。",
        why="挺括外层提供形状，柔软内层负责贴身与舒适；两者形成骨架加填充的关系。材质对比让外轮廓立住，又不牺牲内层的活动量。",
        how_to_judge="摸外层是否有骨架（牛仔、皮革、尼龙、羊毛、帆布、防水涂层），再摸内层是否柔软（棉、针织、亚麻、化纤、缎面、麂皮）。",
        grade="C",
        source="服装造型中 structure vs drape 的通行区分",
        rule_ids=("R-MAT-01",),
        axis="texture",
        status="dormant",
    ),
    # 图案
    _p(
        id="P-PAT-01",
        title="全身只保留一个图案焦点",
        claim="全身大图案不超过 1 件；如果只有一件，让它落在视觉主体位（外套或下装），其余保持纯色。",
        why="图案自带注意力。两件大图案会互相争夺焦点；一件大图案放在外套或下装，能把视线引到想强调的区域，其余纯色提供留白。",
        how_to_judge="先数大图案件数，超过 1 件就删；只有 1 件时，看它是不是在外套或下装，其余是不是纯色。",
        grade="B",
        source="Gestalt 图底关系；造型教学中的一个 statement piece",
        rule_ids=("R-PAT-01", "R-PAT-02"),
        axis="pattern",
        status="dormant",
    ),
)

UNSUPPORTED: tuple[UnsupportedTopic, ...] = (
    UnsupportedTopic(
        topic="60-30-10 精确面积比例",
        why="当前没有单品在身上的可见面积，只能判主色 ≤3。",
        needed="单品可见面积估算或遮挡面积",
    ),
    UnsupportedTopic(
        topic="个人色彩季型 / 冷暖肤色",
        why="没有肤色、发色与试色记录。",
        needed="肤色/发色字段与试色照片",
    ),
    UnsupportedTopic(
        topic="身材类型（A/H/X/Y/O）",
        why="没有肩宽/臀宽比例、腰围与内长。",
        needed="腰围、内长、肩宽与臀宽比例",
    ),
    UnsupportedTopic(
        topic="腿长比例与腰线位置",
        why="没有内缝长与腰高。",
        needed="内长、裤裆深、腰线高",
    ),
    UnsupportedTopic(
        topic="图案尺度、方向、位置",
        why="只有 pattern=bold 计数，没有图案尺寸与分布。",
        needed="图案尺寸、方向与分布字段",
    ),
    UnsupportedTopic(
        topic="面料纹理、垂坠、光泽",
        why="material 只有粗分类，VLM 材质准确率约 67%。",
        needed="更细的材质与克重字段",
    ),
    UnsupportedTopic(
        topic="鞋型、鞋跟、鞋头",
        why="当前只有鞋的材质与颜色。",
        needed="鞋型/鞋头/跟高字段",
    ),
    UnsupportedTopic(
        topic="配饰、包、腰带",
        why="当前没有配饰品类，规则不消费。",
        needed="配饰类型与颜色字段",
    ),
    UnsupportedTopic(
        topic="极简/街头/法式等风格原型",
        why="没有 style tags、品牌或版型数据。",
        needed="风格标签或品牌/版型数据",
    ),
    UnsupportedTopic(
        topic="地区着装差异",
        why="当前只有单用户、单地点。",
        needed="多地点与场合画像",
    ),
)

PRINCIPLE_BY_ID: dict[str, Principle] = {p.id: p for p in PRINCIPLES}

PRINCIPLES_BY_RULE: dict[str, tuple[Principle, ...]] = {
    rule_id: tuple(p for p in PRINCIPLES if rule_id in p.rule_ids)
    for rule_id in RULE_NAMES
}

DISPLAY_ORDER: tuple[str, ...] = tuple(
    p.id for axis in AXIS_ORDER for p in PRINCIPLES if p.axis == axis
)


def _validate() -> None:
    ids = [p.id for p in PRINCIPLES]
    assert len(PRINCIPLES) == 18, f"原理条数应为 18，实际 {len(PRINCIPLES)}"
    assert len(ids) == len(set(ids)), "P-ID 重复"
    for principle in PRINCIPLES:
        assert _ID_RE.match(principle.id), f"P-ID 格式不合法：{principle.id}"
        assert principle.grade in _GRADES, f"{principle.id} 依据等级不合法"
        assert principle.status in _STATUSES, f"{principle.id} 状态不合法"
        assert principle.axis in AXIS_ORDER, f"{principle.id} 轴不合法"
        assert principle.rule_ids, f"{principle.id} 没有映射规则"
        for rule_id in principle.rule_ids:
            assert rule_id in RULE_NAMES, f"{principle.id} 引用了未知规则 {rule_id}"
        if principle.source_url is not None:
            assert principle.source_url.startswith("https://"), (
                f"{principle.id} 来源链接必须为 https"
            )
    covered = {rid for p in PRINCIPLES for rid in p.rule_ids}
    missing = set(RULE_NAMES) - covered
    assert not missing, f"以下规则没有被任何原理覆盖：{sorted(missing)}"
    assert set(PRINCIPLES_BY_RULE) == set(RULE_NAMES)
    assert all(PRINCIPLES_BY_RULE[rid] for rid in RULE_NAMES), "存在没有原理的规则"
    assert len(DISPLAY_ORDER) == len(PRINCIPLES), "展示顺序遗漏原理"


_validate()
