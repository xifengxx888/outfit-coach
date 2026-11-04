#!/usr/bin/env python3
"""生成 A4 拍摄标定卡（300 DPI，按 100% 打印）。

元素：
  - 5cm ArUco DICT_4X4_50 标记（黑框外沿 = 50.0mm）
  - 100mm 校准尺（打印后先量它）
  - 18% 灰块 + 白块（白平衡/曝光）
  - 6 个色块（RGB 三原色 + 肤色 + 深灰 + 浅灰）

运行（临时环境，不写进项目依赖）：
  cd ~/claude/个人穿搭助手
  uv run --python 3.12 --with opencv-contrib-python-headless --with pillow \
    scripts/spike/make_calibration_card.py

输出：
  scripts/spike/calibration_card_a4.png
  scripts/spike/calibration_card_a4.pdf
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 300
MM_PER_INCH = 25.4
PX_PER_MM = DPI / MM_PER_INCH  # 11.811 px/mm
A4_W_MM, A4_H_MM = 210, 297
W, H = round(A4_W_MM * PX_PER_MM), round(A4_H_MM * PX_PER_MM)  # 2480 × 3508
MARKER_MM = 50.0
MARKER_PX = round(MARKER_MM * PX_PER_MM)  # 591 px

OUT_DIR = Path(__file__).resolve().parent
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

INK = (26, 26, 26)
MUTED = (95, 95, 95)
LINE = (150, 150, 150)
ACCENT = (180, 40, 40)


def mm(v: float) -> int:
    return round(v * PX_PER_MM)


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size=size, index=0)
            except OSError:
                continue
    print("⚠️  未找到中文字体，卡片文字将退化为英文。")
    return ImageFont.load_default()


def text(draw: ImageDraw.ImageDraw, xy, s: str, font, fill=INK, anchor="la"):
    draw.text(xy, s, font=font, fill=fill, anchor=anchor)


def dashed_rect(draw, box, dash=14, gap=10, width=3, fill=LINE):
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash + gap):
        draw.line([(x, y0), (min(x + dash, x1), y0)], fill=fill, width=width)
        draw.line([(x, y1), (min(x + dash, x1), y1)], fill=fill, width=width)
    for y in range(y0, y1, dash + gap):
        draw.line([(x0, y), (x0, min(y + dash, y1))], fill=fill, width=width)
        draw.line([(x1, y), (x1, min(y + dash, y1))], fill=fill, width=width)


def make_marker() -> Image.Image:
    """生成 ArUco 标记。返回图像边长即黑框外沿尺寸。"""
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker_id = 23
    # OpenCV 5.x
    if hasattr(cv2.aruco, "generateImageMarker"):
        arr = cv2.aruco.generateImageMarker(dictionary, marker_id, MARKER_PX, borderBits=1)
    else:  # OpenCV 4.x 旧接口
        arr = cv2.aruco.drawMarker(dictionary, marker_id, MARKER_PX, 1)
    if arr.shape[:2] != (MARKER_PX, MARKER_PX):
        arr = cv2.resize(arr, (MARKER_PX, MARKER_PX), interpolation=cv2.INTER_NEAREST)
    return Image.fromarray(arr).convert("RGB")


def draw_ruler(draw, x0: int, y: int, length_mm: int = 100):
    x1 = x0 + mm(length_mm)
    draw.line([(x0, y), (x1, y)], fill=INK, width=4)
    for mmark in range(0, length_mm + 1, 5):
        x = x0 + mm(mmark)
        major = mmark % 10 == 0
        tick = 34 if major else 18
        draw.line([(x, y), (x, y - tick)], fill=INK, width=3 if major else 2)
    label_font = load_font(28)
    for mmark in range(0, length_mm + 1, 20):
        x = x0 + mm(mmark)
        text(draw, (x, y + 10), str(mmark), label_font, MUTED, anchor="ma")
    text(draw, (x1 + 20, y + 6), "mm", label_font, MUTED, anchor="la")


def main() -> None:
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    f_title = load_font(78)
    f_sub = load_font(34)
    f_body = load_font(38)
    f_small = load_font(28)
    f_label = load_font(32)
    f_tiny = load_font(24)

    # 标题
    text(draw, (mm(14), mm(12)), "个人穿搭助手 · 拍摄标定卡", f_title)
    text(
        draw,
        (mm(14), mm(24)),
        "打印：A4 · 100%（实际大小）· 关闭「适合页面 / 缩放」",
        f_sub,
        MUTED,
    )

    # ArUco
    # 标记四周留 ≥1 个模块（591 / 6 ≈ 98px ≈ 8.3mm）的纯白静区；
    # 静区内不放文字、不画边框，否则直接拉低识别率。
    marker_x, marker_y = mm(15), mm(38)
    marker = make_marker()
    img.paste(marker, (marker_x, marker_y))
    text(
        draw,
        (marker_x, marker_y + MARKER_PX + mm(12)),
        f"ArUco DICT_4X4_50 · 黑框外沿 = {MARKER_MM:.1f}mm",
        f_label,
    )
    text(
        draw,
        (marker_x, marker_y + MARKER_PX + mm(17)),
        "ID 23 · 拍摄时四角都要入镜",
        f_small,
        MUTED,
    )

    # 校准尺
    ruler_x = mm(82)
    ruler_y = mm(44)
    text(draw, (ruler_x, ruler_y - mm(14)), "校准尺：先量这里", f_label)
    draw_ruler(draw, ruler_x, ruler_y, 100)
    text(
        draw,
        (ruler_x, ruler_y + mm(8)),
        "0 → 100 刻度间距必须是 100.0mm；不是就重新打印",
        f_small,
        MUTED,
    )

    # 灰卡 / 白卡
    patch = mm(32)
    gray_x, gray_y = ruler_x, mm(66)
    draw.rectangle([gray_x, gray_y, gray_x + patch, gray_y + patch], fill=(118, 118, 118))
    draw.rectangle([gray_x, gray_y, gray_x + patch, gray_y + patch], outline=INK, width=2)
    text(draw, (gray_x, gray_y + patch + mm(3)), "18% 灰", f_small)
    text(draw, (gray_x, gray_y + patch + mm(8)), "#767676", f_tiny, MUTED)

    white_x = gray_x + patch + mm(18)
    draw.rectangle([white_x, gray_y, white_x + patch, gray_y + patch], fill="white", outline=INK, width=3)
    text(draw, (white_x, gray_y + patch + mm(3)), "白", f_small)
    text(draw, (white_x, gray_y + patch + mm(8)), "#FFFFFF", f_tiny, MUTED)

    # 色块
    colors = [
        ("红", "#FF0000", (255, 0, 0)),
        ("绿", "#00FF00", (0, 255, 0)),
        ("蓝", "#0000FF", (0, 0, 255)),
        ("肤色", "#E0AC69", (224, 172, 105)),
        ("深灰", "#333333", (51, 51, 51)),
        ("浅灰", "#CCCCCC", (204, 204, 204)),
    ]
    sw = mm(25)
    gap = mm(5)
    cx, cy = mm(15), mm(118)
    for i, (name, hexv, rgb) in enumerate(colors):
        x = cx + i * (sw + gap)
        draw.rectangle([x, cy, x + sw, cy + sw], fill=rgb, outline=INK, width=2)
        text(draw, (x, cy + sw + mm(3)), name, f_small)
        text(draw, (x, cy + sw + mm(8)), hexv, f_tiny, MUTED)

    # 拍摄说明
    ix, iy = mm(15), mm(160)
    text(draw, (ix, iy), "拍摄时怎么做", f_label)
    lines = [
        "① 卡平放在衣服旁边，和衣服同一平面，不要压在衣服上。",
        "② 自然光、白墙、正上方垂直拍；卡的四角都要入镜。",
        "③ 避开反光、阴影和彩色物体；卡不要弯折。",
        "④ 拍完先看：卡上的 100mm 尺和衣服是否都清晰。",
    ]
    for i, line in enumerate(lines):
        text(draw, (ix, iy + mm(11) + i * mm(11)), line, f_body)

    # 识别失败提示
    box_y = mm(220)
    draw.rounded_rectangle(
        [ix, box_y, W - mm(15), box_y + mm(20)],
        radius=mm(3),
        outline=LINE,
        width=2,
    )
    text(draw, (ix + mm(5), box_y + mm(4)), "识别不到 ArUco 怎么办", f_small)
    text(
        draw,
        (ix + mm(5), box_y + mm(11)),
        "尺寸改为手填，不阻塞录入；颜色校正仍然需要这张卡的灰块。",
        f_small,
        MUTED,
    )

    # 页脚
    foot_y = H - mm(22)
    draw.line([(mm(15), foot_y - mm(6)), (W - mm(15), foot_y - mm(6))], fill=LINE, width=2)
    text(
        draw,
        (mm(15), foot_y),
        "2026-10-25 · 版本 1 · 按 100% 打印；标定卡只用于比例与色彩校正，不用于判断搭配",
        f_tiny,
        MUTED,
    )

    png_path = OUT_DIR / "calibration_card_a4.png"
    pdf_path = OUT_DIR / "calibration_card_a4.pdf"
    img.save(png_path, dpi=(DPI, DPI))
    img.save(pdf_path, "PDF", resolution=DPI)
    print(f"✅ {png_path}  ({W}×{H}px @ {DPI}dpi)")
    print(f"✅ {pdf_path}  (A4)")


if __name__ == "__main__":
    main()
