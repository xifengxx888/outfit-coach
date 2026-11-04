"""把量衣表格（xlsx / CSV 行）解析成 `Item`。

纯解析：不连数据库、不写文件。中文枚举的同义词在这里归一化，
具体表结构见 `docs/08-量衣与填表教程.html` 与 `scripts/spike/items_template.xlsx`。

坏行不抛异常，收进 `warnings` 后跳过——量衣是一行一行填的，
一行填错不应该让另外 17 行导不进去。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from ..rules.color_math import hex_to_rgb
from ..rules.slots import CATEGORY_SLOTS
from ..rules.types import (
    BOTTOM_CATEGORIES,
    CATEGORIES,
    FITS,
    LAYERS,
    PATTERNS,
    SEASONS,
    STATUSES,
    WEIGHTS,
    Item,
)

ENUM_SYNONYMS = {
    # 版型
    "修身": "slim",
    "合身": "regular",
    "宽松": "oversize",
    "常规": "regular",
    # 图案
    "纯色": "solid",
    "细纹": "fine",
    "大图案": "bold",
    "大花纹": "bold",
    # 厚度
    "薄": "thin",
    "中": "medium",
    "中等": "medium",
    "厚": "thick",
    # 层级
    "内层": "inner",
    "中层": "mid",
    "外层": "outer",
    "下装": "bottom",
    "鞋": "shoes",
    "鞋子": "shoes",
    "配饰": "accessory",
    # 空值
    "不确定": "",
    "不适用": "",
    "无": "",
    "": "",
}

SHEET_NAME = "填写"


@dataclass
class ParseResult:
    items: list[Item] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def norm_enum(value: object) -> str:
    v = "" if value is None else str(value).strip()
    if v in ENUM_SYNONYMS:
        return ENUM_SYNONYMS[v]
    return v.lower() if v.isascii() else v


def split_multi(value: object) -> tuple[str, ...]:
    """拆多值单元格：中英文逗号、顿号、斜杠都算分隔符，去重保序。"""
    raw = ("" if value is None else str(value)).replace("，", "/").replace(",", "/")
    raw = raw.replace("、", "/")
    parts = [norm_enum(p) for p in raw.split("/") if p.strip()]
    return tuple(dict.fromkeys(parts))


def parse_float(value: object) -> float | None:
    v = ("" if value is None else str(value)).strip().lower().replace("cm", "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_rows(path: str | Path) -> list[dict[str, str]]:
    """读 xlsx 的「填写」页，统一成「列名 → 去空白字符串」。空单元格为空串。"""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME] if SHEET_NAME in wb.sheetnames else wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        raise ValueError(f"空文件：{path}")
    header = [str(h).strip() if h is not None else "" for h in header]
    if "名称" not in header:
        raise ValueError(f"表头缺「名称」列：{path}")
    return [
        {h: "" if v is None else str(v).strip() for h, v in zip(header, raw)}
        for raw in rows
    ]


def parse_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    default_status: str = "draft",
) -> ParseResult:
    """逐行解析。行号按表格行计（首行表头，数据从第 2 行起）。"""
    if default_status not in STATUSES:
        raise ValueError(f"未知状态：{default_status!r}")
    result = ParseResult()
    warnings = result.warnings
    seen_ids: set[int] = set()

    for row_no, row in enumerate(rows, start=2):
        name = str(row.get("名称") or "").strip()
        if not name or name.startswith("示例"):
            continue  # 空行与模板示例行，静默跳过

        category = str(row.get("品类") or "").strip()
        if category not in CATEGORIES:
            warnings.append(f"第 {row_no} 行「{name}」品类未知（{category!r}），已跳过")
            continue

        layers = split_multi(row.get("层级"))
        bad_layers = [layer for layer in layers if layer not in LAYERS]
        if bad_layers:
            warnings.append(
                f"第 {row_no} 行「{name}」层级未知（{bad_layers}），已跳过"
            )
            continue
        if category not in CATEGORY_SLOTS and not layers:
            warnings.append(
                f"第 {row_no} 行「{name}」层级为空，放不进任何槽位，已跳过"
            )
            continue

        try:
            formality = int(float(row.get("正式度") or ""))
        except ValueError:
            warnings.append(f"第 {row_no} 行「{name}」正式度不是 1–5，已跳过")
            continue
        if not 1 <= formality <= 5:
            warnings.append(f"第 {row_no} 行「{name}」正式度 {formality} 超出 1–5，已跳过")
            continue

        fit = norm_enum(row.get("版型"))
        pattern = norm_enum(row.get("图案"))
        weight = norm_enum(row.get("厚度"))
        if fit not in FITS or pattern not in PATTERNS or weight not in WEIGHTS:
            warnings.append(
                f"第 {row_no} 行「{name}」版型/图案/厚度不完整"
                f"（{fit}/{pattern}/{weight}），已跳过"
            )
            continue

        color_hex = str(row.get("颜色HEX") or "").strip()
        try:
            hex_to_rgb(color_hex)
        except ValueError:
            warnings.append(f"第 {row_no} 行「{name}」颜色 HEX 无效，已跳过")
            continue

        item_id = _resolve_id(row.get("编号"), row_no, seen_ids, warnings, name, row_no)
        seen_ids.add(item_id)

        seasons = split_multi(row.get("季节"))
        bad_seasons = [s for s in seasons if s not in SEASONS]
        if bad_seasons:
            warnings.append(
                f"第 {row_no} 行「{name}」季节未知（{bad_seasons}），已忽略这些值"
            )
            seasons = tuple(s for s in seasons if s in SEASONS)

        is_bottom = category in BOTTOM_CATEGORIES
        length = parse_float(row.get("裤长cm") if is_bottom else row.get("衣长cm"))
        if is_bottom and length is None:
            length = parse_float(row.get("衣长cm"))

        result.items.append(
            Item(
                id=item_id,
                name=name,
                category=category,
                layers=layers,
                formality=formality,
                color_hex=color_hex,
                fit=fit,
                pattern=pattern,
                weight=weight,
                material=norm_enum(row.get("材质")) or None,
                collar=norm_enum(row.get("领型")) or None,
                length_cm=length,
                shoulder_cm=parse_float(row.get("肩宽cm")),
                chest_width_cm=parse_float(row.get("胸宽cm")),
                sleeve_cm=parse_float(row.get("袖长cm")),
                waist_cm=parse_float(row.get("平铺腰围cm")),
                hip_cm=parse_float(row.get("平铺臀围cm")),
                leg_opening_cm=parse_float(row.get("脚口宽cm")),
                seasons=seasons,
                photo_path=str(row.get("照片文件名") or "").strip() or None,
                status=default_status,
                source="manual",
            )
        )
    return result


def _resolve_id(
    raw_id: object,
    fallback: int,
    seen_ids: set[int],
    warnings: list[str],
    name: str,
    row_no: int,
) -> int:
    text = str(raw_id or "").strip()
    try:
        item_id = int(float(text)) if text else fallback
    except ValueError:
        item_id = fallback
    if item_id in seen_ids:
        warnings.append(f"第 {row_no} 行「{name}」编号 {item_id} 重复，改为 {fallback}")
        item_id = fallback
        while item_id in seen_ids:
            item_id += 1
    return item_id
