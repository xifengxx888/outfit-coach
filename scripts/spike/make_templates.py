#!/usr/bin/env python3
"""生成 10 件衣柜干跑的属性模板。

输出：
  scripts/spike/items_template.xlsx  ← 主用，带下拉、示例与填写说明
  scripts/spike/items_template.csv   ← 备份，UTF-8 BOM，Excel 可直接打开

运行：
  uv run --python 3.12 --with openpyxl scripts/spike/make_templates.py
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT_DIR = Path(__file__).resolve().parent

HEADERS = [
    "编号",
    "名称",
    "品类",
    "层级",
    "正式度",
    "颜色HEX",
    "版型",
    "图案",
    "材质",
    "领型",
    "厚度",
    "衣长cm",
    "肩宽cm",
    "胸宽cm",
    "袖长cm",
    "裤长cm",
    "平铺腰围cm",
    "平铺臀围cm",
    "脚口宽cm",
    "季节",
    "照片文件名",
    "备注",
]

CATEGORIES = [
    "T恤", "衬衫", "卫衣", "毛衣", "针织", "外套", "夹克", "西装",
    "裤子", "牛仔裤", "短裤", "鞋", "配饰", "连体装", "西装套装",
]
LAYERS = ["inner", "mid", "outer", "bottom", "shoes", "accessory"]
FORMALITY = ["1", "2", "3", "4", "5"]
FITS = ["slim", "regular", "oversize"]
PATTERNS = ["solid", "fine", "bold"]
MATERIALS = [
    "棉", "羊毛", "针织", "牛仔", "皮革", "尼龙", "亚麻", "化纤",
    "麂皮", "帆布", "缎面", "橡胶", "防水涂层", "不确定",
]
COLLARS = ["圆领", "高领", "V领", "翻领", "连帽", "无领", "不适用", "不确定"]
WEIGHTS = ["thin", "medium", "thick"]
SEASONS = ["summer", "spring_fall", "winter"]

REQUIRED = {"编号", "名称", "品类", "层级", "正式度", "颜色HEX", "版型", "图案", "厚度"}

EXAMPLES = [
    ["1", "白色棉T恤", "T恤", "inner", 2, "#F2F2F2", "regular", "solid", "棉", "圆领", "thin",
     68, 44, 50, 20, "", "", "", "", "summer", "tshirt_white.jpg", "合身，手量"],
    ["2", "深蓝牛仔外套", "外套", "outer", 3, "#3A4A63", "regular", "solid", "牛仔", "翻领", "medium",
     66, 45, 54, 61, "", "", "", "", "spring_fall", "denim_jacket.jpg", "外套 4 项已手量"],
    ["3", "卡其直筒裤", "裤子", "bottom", 3, "#C3B091", "regular", "solid", "棉", "不适用", "medium",
     "", "", "", "", 100, 40, 50, 19, "spring_fall", "khaki_pants.jpg", "裤子 4 项已手量"],
]

THIN = Side(style="thin", color="D0D0D0")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
OPTIONAL_FILL = PatternFill("solid", fgColor="5B7DB1")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
NOTE_FONT = Font(color="666666", size=10)


def write_template_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "填写"

    ws.append(HEADERS)
    for idx, name in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=idx)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL if name in REQUIRED else OPTIONAL_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(idx)].width = 13 if name != "名称" else 22
        if name == "备注":
            ws.column_dimensions[get_column_letter(idx)].width = 28

    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"

    # 20 行空白，够 10 件干跑，也够之后继续补
    for row in range(2, 22):
        for col in range(1, len(HEADERS) + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center")

    def add_dv(col_name: str, options: list[str], allow_custom: bool = False) -> None:
        col = get_column_letter(HEADERS.index(col_name) + 1)
        dv = DataValidation(
            type="list",
            formula1='"' + ",".join(options) + '"',
            allow_blank=True,
            showErrorMessage=not allow_custom,
        )
        dv.error = "请从下拉列表中选择"
        dv.errorTitle = "取值不在枚举内"
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}31")

    add_dv("品类", CATEGORIES)
    add_dv("层级", LAYERS, allow_custom=True)  # 多值：inner/mid
    add_dv("正式度", FORMALITY)
    add_dv("版型", FITS)
    add_dv("图案", PATTERNS)
    add_dv("材质", MATERIALS)
    add_dv("领型", COLLARS)
    add_dv("厚度", WEIGHTS)
    add_dv("季节", SEASONS, allow_custom=True)  # 多值：summer/spring_fall

    # 示例表
    ex = wb.create_sheet("示例（照着填）")
    ex.append(HEADERS)
    for cell in ex[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    for row in EXAMPLES:
        ex.append(row)
    for row in ex.iter_rows(min_row=2, max_row=ex.max_row, max_col=len(HEADERS)):
        for cell in row:
            cell.border = BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for idx, name in enumerate(HEADERS, start=1):
        ex.column_dimensions[get_column_letter(idx)].width = 13 if name != "名称" else 22
    ex.row_dimensions[1].height = 34
    ex.freeze_panes = "A2"

    # 说明表
    info = wb.create_sheet("填写说明")
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 98

    rows = [
        ("用途", "按 02 的 item schema 填 10 件真实单品，保存后运行 scripts/spike/dryrun.py。"),
        ("图文教程", "docs/08-量衣与填表教程.html：8 个尺寸的测量位置图、颜色取色器、字段速查与 10 件清单。"),
        ("必填", "编号 / 名称 / 品类 / 层级 / 正式度 / 颜色HEX / 版型 / 图案 / 厚度。深蓝色表头是必填，浅蓝色是选填。"),
        ("选填但建议填", "材质、领型。各是一个下拉，填了才能让 R-MAT-01 / R-SHO-03 / R-LYR-03 生效；不填只是跳过，不算错。"),
        ("这轮不用填", "季节（只用于展示）、照片文件名（仅备查）、备注（随便写）。"),
        ("尺寸用在哪", "干跑只读「衣长」：外套衣长影响 R-PRP-04，上装三层衣长影响 R-LYR-02。肩宽/胸宽/袖长/平铺腰围/臀围/脚口本脚本不读，但 M1 建库要用，建议这次一起量。"),
        ("条件必填", "外套：衣长、肩宽、胸宽、袖长 4 项；裤子：裤长、平铺腰围、臀围、脚口 4 项。缺了不会让整行作废，只是对应软规则跳过；但 M1 建库要用，建议一次量全。"),
        ("层级", "inner / mid / outer / bottom / shoes / accessory。多值用 / 分隔，表示“可以当内层，也可以当中层”，不是同时穿两层。连体装、西装套装留空。"),
        ("正式度", "1 运动 / 2 休闲 / 3 日常 / 4 商务休闲 / 5 正装。"),
        ("版型", "slim 修身 / regular 合身 / oversize 宽松。"),
        ("图案", "solid 纯色 / fine 细纹 / bold 大图案。"),
        ("材质", "人工选，不靠模型猜。不确定就填“不确定”，相关规则会跳过，不会误判。"),
        ("领型", "用于 R-LYR-03（双高领扣分）。裤子、鞋填“不适用”；不确定填“不确定”。"),
        ("厚度", "thin 薄 / medium 中 / thick 厚。按手感，不按季节。"),
        ("颜色HEX", "填 #RRGGBB。有标定卡就填校正后的主色；没有就填肉眼主色，并在备注写“未校正”。"),
        ("衣长", "后领中点（衬衫取领座下缘，T恤/卫衣取罗纹领条下缘，不含领子）→ 下摆最底边。裤子的“衣长”留空，改填“裤长”。"),
        ("肩宽", "平铺，左右肩缝端点之间。插肩袖没有肩缝，留空并备注“插肩”。"),
        ("胸宽", "平铺，左右腋点之间，不乘 2。"),
        ("袖长", "肩缝端点 → 袖口边缘。插肩袖从后领中点量，备注“插肩袖长”。"),
        ("裤长", "腰头侧缝处 → 裤脚底边。"),
        ("平铺腰围", "腰头左右两端之间，不乘 2。松紧腰自然平放，不要拉直。"),
        ("平铺臀围", "裤子平铺、拉链拉好、前片朝上。从腰头上沿往下 7–10cm，找到最宽的胯部，左右侧缝之间横量，不乘 2。最宽点若不在此高度，量最宽处并在备注写高度。参考 48–54cm。"),
        ("脚口宽", "平铺，只量一条裤腿的裤脚，从左到右横量，不乘 2，不绕圈量周长。翻边裤按翻好的穿着状态量；松紧脚口自然平放，不拉伸。参考：修身 16–18 / 直筒 18–21 / 阔腿 21–26 / 束脚 12–16cm。"),
        ("季节", "summer / spring_fall / winter，多值用 /。只用于展示，不参与求解。"),
        ("照片文件名", "对应照片的文件名，便于核对；没有就留空。"),
        ("备注", "写“手量 / 估算 / 未校正 / 版型偏大”这类信息，dryrun 不读，但之后有用。"),
        ("运行干跑", "填完直接存 xlsx，运行：python3 scripts/spike/dryrun.py --items scripts/spike/items_template.xlsx"),
        ("导出 CSV", "可选，直接跑 xlsx 就不需要。真要导出就选「CSV UTF-8」，文件名 items.csv。"),
    ]
    info.append(["项目", "说明"])
    for cell in info[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = BORDER
    for key, value in rows:
        info.append([key, value])
    for row in info.iter_rows(min_row=2, max_row=info.max_row, max_col=2):
        row[0].font = Font(bold=True, size=11)
        row[0].alignment = Alignment(vertical="top")
        row[1].font = NOTE_FONT
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
        for cell in row:
            cell.border = BORDER
        # 说明列宽 98，按中文占 2 个字符宽度估算行高，避免长句被默认行高裁掉
        text = str(row[1].value or "")
        units = sum(2 if ord(ch) > 127 else 1 for ch in text)
        lines = max(1, math.ceil(units / 92))
        info.row_dimensions[row[0].row].height = max(16, 15 * lines + 3)
    info.row_dimensions[1].height = 26
    info.freeze_panes = "A2"

    wb.save(path)


def write_template_csv(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADERS)
        for _ in range(10):
            writer.writerow([""] * len(HEADERS))


def has_filled_rows(path: Path) -> bool:
    """模板一旦被填过，就拒绝覆盖——那里面是真实测量数据。"""
    if not path.exists():
        return False
    try:
        wb = load_workbook(path, read_only=True)
    except Exception:
        return True
    ws = wb["填写"] if "填写" in wb.sheetnames else wb.active
    filled = any(
        cell.value not in (None, "")
        for row in ws.iter_rows(min_row=2, max_col=ws.max_column)
        for cell in row
    )
    wb.close()
    return filled


def main() -> int:
    out_dir = OUT_DIR
    if "--out-dir" in sys.argv:
        idx = sys.argv.index("--out-dir")
        try:
            out_dir = Path(sys.argv[idx + 1]).expanduser().resolve()
        except IndexError:
            print("--out-dir 需要一个目录参数", file=sys.stderr)
            return 2
    force = "--force" in sys.argv

    xlsx_path = out_dir / "items_template.xlsx"
    csv_path = out_dir / "items_template.csv"

    if has_filled_rows(xlsx_path) and not force:
        print(
            f"⛔ {xlsx_path} 已有填写内容，拒绝覆盖。\n"
            "   要生成空白模板，请换目录：--out-dir /tmp/xxx\n"
            "   确认要抹掉现有数据再加 --force。",
            file=sys.stderr,
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    write_template_xlsx(xlsx_path)
    write_template_csv(csv_path)
    print(f"✅ {xlsx_path}")
    print(f"✅ {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
