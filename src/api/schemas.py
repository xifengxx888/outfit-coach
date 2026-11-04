"""录入请求模型：把前端的一张表单变成经过校验的 `Item`。

校验分两层：字段级白名单（品类、层级、版型、颜色……）与整表单规则
（层级与品类是否冲突、confirmed 的尺寸是否齐）。前端做的预检只是体验，
这里是最终口径——规则引擎读到的每一件 confirmed 单品都必须过这一关。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..rules.slots import CATEGORY_SLOTS
from ..rules.types import (
    BOTTOM_CATEGORIES,
    CATEGORIES,
    COLLARS,
    FITS,
    LAYERS,
    MATERIALS,
    NULL_CHOICES,
    PATTERNS,
    WEIGHTS,
    Item,
)

# 按外套口径量的品类。西装套装的裤长口径留到 M2，本轮只量上身四项。
OUTER_CATEGORIES = frozenset({"外套", "夹克", "西装", "西装套装"})
OUTER_DIMS = {
    "length_cm": "衣长",
    "shoulder_cm": "肩宽",
    "chest_width_cm": "胸宽",
    "sleeve_cm": "袖长",
}
# 上衣：衣长、肩宽、胸宽必填；袖长只存档，不拦 confirmed。
TOP_CATEGORIES = frozenset({"T恤", "衬衫", "卫衣", "毛衣", "针织"})
TOP_DIMS = {
    "length_cm": "衣长",
    "shoulder_cm": "肩宽",
    "chest_width_cm": "胸宽",
}
SHOE_CATEGORIES = frozenset({"鞋"})
SHOE_DIMS = {"shoe_size": "鞋码"}
BOTTOM_DIMS = {
    "length_cm": "裤长",
    "waist_cm": "腰围",
    "hip_cm": "臀围",
    "leg_opening_cm": "裤口",
}
# 厚度是季节的唯一来源：M1 不单独填季节，避免两份口径打架
SEASON_BY_WEIGHT = {
    "thin": ("summer",),
    "medium": ("spring_fall",),
    "thick": ("winter",),
}

MAX_PHOTO_CHARS = 12 * 1024 * 1024
MAX_PHOTOS = 6
MAX_DIM_CM = 300.0


def _check_photos(value: list[str]) -> list[str]:
    """多图共用口径：数量、单张体积、空串都在进库前拦下。"""
    if len(value) > MAX_PHOTOS:
        raise ValueError(f"最多 {MAX_PHOTOS} 张照片")
    for raw in value:
        if not raw:
            raise ValueError("照片内容为空")
        if len(raw) > MAX_PHOTO_CHARS:
            raise ValueError("单张照片太大，请重新选择")
    return value


def _optional_choice(value: str | None, allowed: tuple[str, ...], label: str) -> str | None:
    """白名单文本；`不确定` / `不适用` / 空串统一成 None。"""
    if value is None:
        return None
    text = value.strip()
    if text in NULL_CHOICES:
        return None
    if text not in allowed:
        raise ValueError(f"未知{label}：{text}")
    return text


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=60)
    category: str
    layers: list[str] = Field(default_factory=list, max_length=len(LAYERS))
    formality: int = Field(ge=1, le=5)
    color_hex: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    fit: str
    pattern: str
    weight: str
    material: str | None = None
    collar: str | None = None
    length_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    shoulder_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    chest_width_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    sleeve_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    waist_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    hip_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    leg_opening_cm: float | None = Field(default=None, gt=0, le=MAX_DIM_CM)
    shoe_size: float | None = Field(default=None, gt=0, le=60)
    photos_data: list[str] = Field(default_factory=list)
    status: Literal["confirmed", "draft"] = "confirmed"

    @field_validator("category")
    @classmethod
    def _check_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"未知品类：{value}")
        return value

    @field_validator("fit")
    @classmethod
    def _check_fit(cls, value: str) -> str:
        if value not in FITS:
            raise ValueError(f"未知版型：{value}")
        return value

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, value: str) -> str:
        if value not in PATTERNS:
            raise ValueError(f"未知图案：{value}")
        return value

    @field_validator("weight")
    @classmethod
    def _check_weight(cls, value: str) -> str:
        if value not in WEIGHTS:
            raise ValueError(f"未知厚度：{value}")
        return value

    @field_validator("layers")
    @classmethod
    def _check_layers(cls, value: list[str]) -> list[str]:
        bad = [layer for layer in value if layer not in LAYERS]
        if bad:
            raise ValueError(f"未知层级：{'、'.join(bad)}")
        if len(set(value)) != len(value):
            raise ValueError("层级不能重复")
        return value

    @field_validator("material")
    @classmethod
    def _check_material(cls, value: str | None) -> str | None:
        return _optional_choice(value, MATERIALS, "材质")

    @field_validator("collar")
    @classmethod
    def _check_collar(cls, value: str | None) -> str | None:
        return _optional_choice(value, COLLARS, "领型")

    @field_validator("photos_data")
    @classmethod
    def _check_photo_list(cls, value: list[str]) -> list[str]:
        return _check_photos(value)

    def required_dims(self) -> dict[str, str]:
        """该品类必须量的尺寸：外套四项、上衣三项、裤四项、鞋鞋码。"""
        if self.category in OUTER_CATEGORIES:
            return OUTER_DIMS
        if self.category in TOP_CATEGORIES:
            return TOP_DIMS
        if self.category in BOTTOM_CATEGORIES:
            return BOTTOM_DIMS
        if self.category in SHOE_CATEGORIES:
            return SHOE_DIMS
        return {}

    def missing_dims(self) -> list[str]:
        labels = self.required_dims()
        return [
            label
            for field_name, label in labels.items()
            if getattr(self, field_name) is None
        ]

    @model_validator(mode="after")
    def _check_consistency(self) -> "ItemIn":
        if self.category in CATEGORY_SLOTS:
            if self.layers:
                raise ValueError(f"{self.category}的槽位由品类决定，不要选层级")
        elif not self.layers:
            raise ValueError("至少选一个层级")
        if self.status == "confirmed":
            missing = self.missing_dims()
            if missing:
                raise ValueError("存为已确认需要先量：" + "、".join(missing))
        return self

    def to_item(
        self,
        item_id: int,
        photo_path: str | None,
        extra_photos: tuple[str, ...] = (),
    ) -> Item:
        return Item(
            id=item_id,
            name=self.name,
            category=self.category,
            layers=tuple(self.layers),
            formality=self.formality,
            color_hex=self.color_hex.upper(),
            fit=self.fit,
            pattern=self.pattern,
            weight=self.weight,
            material=self.material,
            collar=self.collar,
            length_cm=self.length_cm,
            shoulder_cm=self.shoulder_cm,
            chest_width_cm=self.chest_width_cm,
            sleeve_cm=self.sleeve_cm,
            waist_cm=self.waist_cm,
            hip_cm=self.hip_cm,
            leg_opening_cm=self.leg_opening_cm,
            shoe_size=self.shoe_size,
            seasons=SEASON_BY_WEIGHT[self.weight],
            photo_path=photo_path,
            extra_photos=extra_photos,
            status=self.status,
            source="manual",
            last_worn_at=None,
        )


class ItemPatch(BaseModel):
    """编辑补丁：只校验类型与取值域，整表规则合并后交给 `ItemIn`。

    `model_fields_set` 用来区分「没传」与「显式传 null」——后者对
    `material / collar / 尺寸` 表示清空，对必填字段会在 `ItemIn` 里被拒。
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = None
    category: str | None = None
    layers: list[str] | None = None
    formality: int | None = None
    color_hex: str | None = None
    fit: str | None = None
    pattern: str | None = None
    weight: str | None = None
    material: str | None = None
    collar: str | None = None
    length_cm: float | None = None
    shoulder_cm: float | None = None
    chest_width_cm: float | None = None
    sleeve_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    leg_opening_cm: float | None = None
    shoe_size: float | None = None
    photos_data: list[str] | None = None
    status: Literal["confirmed", "draft", "archived"] | None = None

    @field_validator("photos_data")
    @classmethod
    def _check_photo_list(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _check_photos(value)


__all__ = [
    "BOTTOM_DIMS",
    "ItemIn",
    "ItemPatch",
    "MAX_PHOTOS",
    "OUTER_DIMS",
    "SEASON_BY_WEIGHT",
    "SHOE_DIMS",
    "TOP_DIMS",
]
