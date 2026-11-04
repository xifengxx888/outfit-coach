"""导入解析单测：枚举归一化、坏行跳过、量长取值与状态。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import Workbook
from src.db.importer import load_rows, parse_rows

VALID_ROW: dict[str, Any] = {
    "编号": "1",
    "名称": "灰色长袖衬衫",
    "品类": "衬衫",
    "层级": "inner",
    "正式度": "3",
    "颜色HEX": "#808080",
    "版型": "合身",
    "图案": "纯色",
    "材质": "不确定",
    "领型": "不适用",
    "厚度": "薄",
    "衣长cm": "70",
    "肩宽cm": "44",
    "胸宽cm": "51",
    "袖长cm": "60",
    "裤长cm": "",
    "平铺腰围cm": "",
    "平铺臀围cm": "",
    "脚口宽cm": "",
    "季节": "spring_fall",
    "照片文件名": "pic/6.jpg",
}


def row(**overrides: Any) -> dict[str, Any]:
    merged = dict(VALID_ROW)
    merged.update(overrides)
    return merged


def test_valid_row_is_parsed_and_enums_are_normalized() -> None:
    result = parse_rows([row()])
    assert result.warnings == []
    item = result.items[0]

    assert item.id == 1
    assert item.fit == "regular"
    assert item.pattern == "solid"
    assert item.weight == "thin"
    assert item.material is None
    assert item.collar is None
    assert item.photo_path == "pic/6.jpg"
    assert item.chest_width_cm == 51.0
    assert item.status == "draft"
    assert item.source == "manual"


def test_blank_and_example_rows_are_skipped_silently() -> None:
    result = parse_rows([row(名称=""), row(名称="示例：白T恤")])
    assert result.items == []
    assert result.warnings == []


def test_unknown_category_is_skipped_with_a_warning() -> None:
    result = parse_rows([row(品类="披风")])
    assert result.items == []
    assert "品类未知" in result.warnings[0]


def test_item_without_layers_cannot_enter_any_slot() -> None:
    result = parse_rows([row(层级="")])
    assert result.items == []
    assert "层级为空" in result.warnings[0]


def test_unknown_layer_is_skipped() -> None:
    result = parse_rows([row(层级="inner/underwear")])
    assert result.items == []
    assert "层级未知" in result.warnings[0]


def test_multi_layer_and_multi_season_cells_are_split() -> None:
    result = parse_rows(
        [row(品类="夹克", 层级="mid/outer", 季节="spring_fall，winter")]
    )
    item = result.items[0]
    assert item.layers == ("mid", "outer")
    assert item.seasons == ("spring_fall", "winter")


def test_unknown_season_is_dropped_with_a_warning() -> None:
    result = parse_rows([row(季节="summer/梅雨")])
    assert result.items[0].seasons == ("summer",)
    assert "季节未知" in result.warnings[0]


def test_bottom_length_comes_from_the_pants_column() -> None:
    result = parse_rows(
        [row(品类="牛仔裤", 层级="bottom", 衣长cm="70", 裤长cm="95")]
    )
    assert result.items[0].length_cm == 95.0


def test_bottom_falls_back_to_garment_length_when_pants_length_is_empty() -> None:
    result = parse_rows([row(品类="短裤", 层级="bottom", 衣长cm="45", 裤长cm="")])
    assert result.items[0].length_cm == 45.0


def test_invalid_hex_is_skipped() -> None:
    result = parse_rows([row(颜色HEX="#12345")])
    assert result.items == []
    assert "HEX 无效" in result.warnings[0]


def test_formality_out_of_range_is_skipped() -> None:
    result = parse_rows([row(正式度="6")])
    assert result.items == []
    assert "超出 1–5" in result.warnings[0]


def test_duplicate_id_is_reassigned_to_the_sheet_row() -> None:
    result = parse_rows([row(编号="1"), row(名称="第二件", 编号="1")])
    assert [item.id for item in result.items] == [1, 3]
    assert "编号 1 重复" in result.warnings[0]


def test_status_can_be_overridden() -> None:
    result = parse_rows([row()], default_status="confirmed")
    assert result.items[0].status == "confirmed"


def test_load_rows_reads_the_form_sheet(tmp_path: Path) -> None:
    path = tmp_path / "items.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "填写"
    ws.append(["名称", "品类", "颜色HEX"])
    ws.append(["测试单品", "T恤", "#000000"])
    wb.save(path)

    rows = load_rows(path)
    assert rows == [{"名称": "测试单品", "品类": "T恤", "颜色HEX": "#000000"}]
