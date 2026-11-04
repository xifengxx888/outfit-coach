"""规则引擎的公共类型：单品、上下文、候选组合、规则命中。

`Item` 是**纯数据**：颜色派生属性在构造时一次性算好，之后规则只读不写。
字段名与 `02` 第二节的 `item` 表一一对应，数据库层可以按字段名直接映射。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping

from .color_math import ColorAttrs, color_attrs

# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------

CATEGORIES = (
    "T恤", "衬衫", "卫衣", "毛衣", "针织", "外套", "夹克", "西装",
    "裤子", "牛仔裤", "短裤", "鞋", "配饰", "连体装", "西装套装",
)
BOTTOM_CATEGORIES = frozenset({"裤子", "牛仔裤", "短裤"})

LAYERS = ("inner", "mid", "outer", "bottom", "shoes", "accessory")
FITS = ("slim", "regular", "oversize")
PATTERNS = ("solid", "fine", "bold")
WEIGHTS = ("thin", "medium", "thick")
OCCASIONS = ("日常", "旅游", "见人")
SEASONS = ("summer", "spring_fall", "winter")
STATUSES = ("draft", "confirmed", "archived")
SOURCES = ("vlm", "manual")

# 材质与领型是人工选的文本枚举。录入页给这些选项，写入前把
# 「不确定」「不适用」与空串统一归一为 None（缺失时相关规则跳过）。
MATERIALS = (
    "棉", "羊毛", "针织", "牛仔", "皮革", "尼龙", "亚麻", "化纤",
    "麂皮", "帆布", "缎面", "橡胶", "防水涂层", "不确定",
)
COLLARS = ("圆领", "高领", "V领", "翻领", "连帽", "无领", "不适用", "不确定")
NULL_CHOICES = frozenset({"", "不确定", "不适用"})

# 厚度序（R-LYR-01 比较用）
WEIGHT_IDX = {"thin": 1, "medium": 2, "thick": 3}
# 暖度分：把三档厚度映射到 R-OCC-03 的 1–5 目标尺度
WARMTH = {"thin": 1.0, "medium": 3.0, "thick": 5.0}
# 版型序（R-PRP-03 的宽窄对比按跨度判定）
FIT_IDX = {"slim": 1, "regular": 2, "oversize": 3}
FIT_CN = {"slim": "修身", "regular": "合身", "oversize": "宽松"}


class Status(str, Enum):
    """规则三态。硬规则遇 SKIP 按通过处理，软规则遇 SKIP 不计分。"""

    PASS = "pass"
    SKIP = "skip"
    FAIL = "fail"


class Kind(str, Enum):
    HARD = "hard"
    SOFT = "soft"


class Occasion(str, Enum):
    DAILY = "日常"
    TRAVEL = "旅游"
    MEETING = "见人"


@dataclass(frozen=True)
class RuleHit:
    """一条规则对一套组合的判定结果。"""

    rule_id: str
    kind: Kind
    status: Status
    value: float = 0.0
    reason: str | None = None

    @property
    def is_fail(self) -> bool:
        return self.status is Status.FAIL

    @property
    def is_scored(self) -> bool:
        """软规则只有在 PASS 且 value≠0 时参与加权。"""
        return self.status is Status.PASS and self.value != 0.0


@dataclass(frozen=True)
class Item:
    """一件单品。除 `colors` 外的字段都来自人工确认。

    `layers` 是多值：表示「可以当其中任一层」，不是同时穿两层。
    `length_cm` 缺失时，依赖它的规则返回 SKIP。
    """

    id: int
    name: str
    category: str
    layers: tuple[str, ...]
    formality: int
    color_hex: str
    fit: str
    pattern: str
    weight: str
    material: str | None = None
    collar: str | None = None
    length_cm: float | None = None
    shoulder_cm: float | None = None
    chest_width_cm: float | None = None
    sleeve_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    leg_opening_cm: float | None = None
    extra_photos: tuple[str, ...] = ()
    shoe_size: float | None = None
    seasons: tuple[str, ...] = ()
    photo_path: str | None = None
    cutout_path: str | None = None
    status: str = "confirmed"
    source: str = "manual"
    last_worn_at: str | None = None
    colors: ColorAttrs = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"未知品类：{self.category!r}")
        if not 1 <= self.formality <= 5:
            raise ValueError(f"正式度必须在 1–5：{self.formality!r}")
        if self.fit not in FITS:
            raise ValueError(f"未知版型：{self.fit!r}")
        if self.pattern not in PATTERNS:
            raise ValueError(f"未知图案：{self.pattern!r}")
        if self.weight not in WEIGHTS:
            raise ValueError(f"未知厚度：{self.weight!r}")
        bad_layers = set(self.layers) - set(LAYERS)
        if bad_layers:
            raise ValueError(f"未知层级：{sorted(bad_layers)}")
        # 颜色派生属性只算一次；Item 不可变，不需要失效逻辑
        object.__setattr__(self, "colors", color_attrs(self.color_hex))

    # 便捷属性：规则里读得更短
    @property
    def hue_family(self) -> str:
        return self.colors.hue_family

    @property
    def saturation(self) -> float:
        return self.colors.saturation

    @property
    def lightness(self) -> float:
        return self.colors.lightness

    @property
    def is_neutral(self) -> bool:
        return self.colors.is_neutral

    @property
    def warmth(self) -> str:
        return self.colors.warmth

    @property
    def photos(self) -> tuple[str, ...]:
        """封面在前，追加图在后。照片只留档，规则不读。"""
        return ((self.photo_path,) if self.photo_path else ()) + self.extra_photos


@dataclass(frozen=True)
class Context:
    """求解上下文。由调用方（API / 每日建议）准备好，规则自己不查天气。"""

    occasion: str = Occasion.DAILY.value
    feels_like: float | None = None
    is_rainy: bool = False
    height_cm: float | None = None
    # 身体尺寸：与 profile 同义（胸围/臀围是围度，不是平铺半围）。
    # 缺失时依赖它的合身维度直接跳过，不猜、不扣分。
    shoulder_cm: float | None = None
    chest_cm: float | None = None
    hip_cm: float | None = None
    arm_cm: float | None = None
    # profile 字段名 → 来源（body / garment / estimated），用于按来源降权。
    # 只跟身体数据走；衣件自身的录入方式不参与权重。
    body_sources: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.occasion not in OCCASIONS:
            raise ValueError(f"未知场合：{self.occasion!r}")


@dataclass(frozen=True)
class Candidate:
    """一套槽位合法的组合：`items` 去重后的单品，`placement` 是槽位 → 单品。"""

    items: tuple[Item, ...]
    placement: Mapping[str, Item]

    @property
    def ids(self) -> tuple[int, ...]:
        return tuple(sorted({it.id for it in self.items}))

    def items_in(self, slots: tuple[str, ...]) -> list[Item]:
        """按槽位顺序取单品，同一件占多槽时只出现一次。"""
        seen: set[int] = set()
        out: list[Item] = []
        for slot in slots:
            it = self.placement.get(slot)
            if it is not None and it.id not in seen:
                seen.add(it.id)
                out.append(it)
        return out

    @property
    def name(self) -> str:
        return " + ".join(it.name for it in self.items)


__all__ = [
    "BOTTOM_CATEGORIES",
    "CATEGORIES",
    "COLLARS",
    "Candidate",
    "Context",
    "FITS",
    "FIT_CN",
    "FIT_IDX",
    "Kind",
    "LAYERS",
    "MATERIALS",
    "NULL_CHOICES",
    "OCCASIONS",
    "Occasion",
    "PATTERNS",
    "RuleHit",
    "SEASONS",
    "SOURCES",
    "STATUSES",
    "Status",
    "WARMTH",
    "WEIGHTS",
    "WEIGHT_IDX",
    "Item",
]
