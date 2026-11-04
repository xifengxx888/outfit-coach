#!/usr/bin/env python3
"""门槛 1 · 标定照测量（ArUco 尺度校正 + 衣长/裤长估计）。

三个子命令：
  detect    检测 9 张照片里的 ArUco ID 23，打印像素边长与尺度各向异性
  rectify   用标记四角拟合仿射，把照片校正到标记平面（2 px/mm），输出图供目测
  measure   分割衣物 → 量衣长/裤长 → 与真值对照，写 gate1_result.json

尺度基准**只用 ArUco 标记的实测边长**（50mm × card_scale = 48.5mm）。
标记是印刷在卡上的刚体正方形，四角同时给出尺度与方向，不依赖卡面其他元素的
标称位置。曾试过把六个色块中心一起做 10 点拟合（RANSAC 单应 / LMEDS 仿射）：
单应会因卡面只占画面一小角而外推出离谱的透视项；10 点仿射在 0° 照片上就引入
1%–3% 的尺度各向异性，故两者都弃用。

用法：
  .venv/bin/python scripts/spike/gate1_measure.py detect
  .venv/bin/python scripts/spike/gate1_measure.py rectify
  .venv/bin/python scripts/spike/gate1_measure.py measure
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PHOTO_DIR = ROOT / "pic" / "gate1"
OUT_DIR = Path("/tmp/gate1-warp")
RESULT_PATH = Path(__file__).resolve().parent / "gate1_result.json"
DETECT_PATH = Path(__file__).resolve().parent / "gate1_detect.json"

# 标定卡名义几何（mm），见 make_calibration_card.py
MARKER_ID = 23
MARKER_NOMINAL_MM = 50.0
CARD_SCALE = 0.970  # 2026-10-26 打印实测：100mm 尺读出 97mm，灰块 31/32
MARKER_TRUE_MM = MARKER_NOMINAL_MM * CARD_SCALE  # 48.5
# A4 纸在「标记左上角为原点」的毫米坐标里的范围（已按 card_scale 换算），
# 用来把标定卡自身从衣物掩码里排除——否则黑夹克掩码会吃掉 ArUco 黑框。
CARD_BOX_MM = (-25.0, -45.0, 200.0, 265.0)

# 每件单品：真值（软尺实测，cm）与掩码规则
ITEMS = {
    4: {"name": "tshirt", "truth_cm": 61.7, "kind": "top"},
    11: {"name": "jacket", "truth_cm": 67.0, "kind": "top"},
    13: {"name": "pants", "truth_cm": 95.0, "kind": "pants"},
}

ANGLES = (0, 15, 30)
PHOTOS = {f"{n}.{a}": f"{n}.{a}.jpg" for n in ITEMS for a in ANGLES}


def load(path: Path) -> np.ndarray:
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"读不到图片：{path}")
    return img


def detect_marker(img: np.ndarray):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params = cv2.aruco.DetectorParameters()
    params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, params)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return None
    for c, i in zip(corners, ids.flatten()):
        if int(i) == MARKER_ID:
            return c.reshape(4, 2).astype(np.float64)
    return None


def side_lengths(corners: np.ndarray) -> list[float]:
    return [float(np.linalg.norm(corners[(i + 1) % 4] - corners[i])) for i in range(4)]


MARKER_DST = np.array(
    [[0, 0], [MARKER_TRUE_MM, 0], [MARKER_TRUE_MM, MARKER_TRUE_MM], [0, MARKER_TRUE_MM]],
    dtype=np.float64,
)


def marker_affine(corners: np.ndarray) -> np.ndarray:
    """图像坐标 → 标记毫米坐标（2×3 仿射，无透视项）。"""
    A, _ = cv2.estimateAffine2D(corners, MARKER_DST, method=cv2.LMEDS)
    if A is None:
        raise SystemExit("标记四角无法拟合仿射")
    return A


def marker_homography(corners: np.ndarray) -> np.ndarray:
    """图像坐标 → 标记毫米坐标（3×3 单应）。

    标记与纸面严格共面，四角给满 8 个约束，单应恰好定解、无外推。
    只在标记自身的正方形上拟合，不掺入卡面其他元素——掺进去才会外推出
    离谱的透视项（卡面只占画面一小角，10 点拟合的透视项完全由远端误差主导）。
    """
    return cv2.getPerspectiveTransform(corners.astype(np.float32), MARKER_DST.astype(np.float32))


def map_points(M: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """把 (N,2) 的点用 2×3 仿射或 3×3 单应映射。"""
    if M.shape == (2, 3):
        return pts @ M[:, :2].T + M[:, 2]
    homo = np.hstack([pts, np.ones((len(pts), 1))]) @ M.T
    return homo[:, :2] / homo[:, 2:3]


def affine_scales(A: np.ndarray) -> tuple[float, float]:
    """返回 (sx, sy)：横向与纵向的 px/mm。两者差异即尺度各向异性。"""
    sx = 1.0 / float(np.linalg.norm(A[0, :2]))
    sy = 1.0 / float(np.linalg.norm(A[1, :2]))
    return sx, sy


def rectify(img: np.ndarray, M: np.ndarray, ppm: float = 2.0):
    """把照片送到标记平面，输出 ppm 像素/毫米的图；返回 (图, 左上角毫米坐标, ppm)。"""
    h, w = img.shape[:2]
    ic = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
    mapped = map_points(M, ic)
    x0, y0 = mapped.min(axis=0)
    x1, y1 = mapped.max(axis=0)
    out_w = int(np.ceil((x1 - x0) * ppm))
    out_h = int(np.ceil((y1 - y0) * ppm))
    if M.shape == (2, 3):
        out = cv2.warpAffine(
            img, M * ppm + np.array([[0.0, 0.0, -x0 * ppm], [0.0, 0.0, -y0 * ppm]]),
            (out_w, out_h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255),
        )
    else:
        S = np.array([[ppm, 0, -x0 * ppm], [0, ppm, -y0 * ppm], [0, 0, 1]], dtype=np.float64)
        out = cv2.warpPerspective(
            img, S @ M, (out_w, out_h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255)
        )
    return out, (float(x0), float(y0)), ppm


def cmd_detect() -> None:
    rows = {}
    for key, name in PHOTOS.items():
        img = load(PHOTO_DIR / name)
        corners = detect_marker(img)
        if corners is None:
            rows[key] = {"detected": False}
            print(f"{name:10s} ❌ 未检测到 ArUco ID {MARKER_ID}")
            continue
        sides = side_lengths(corners)
        px_per_mm = float(np.mean(sides)) / MARKER_TRUE_MM
        A = marker_affine(corners)
        sx, sy = affine_scales(A)
        rows[key] = {
            "detected": True,
            "corners": corners.round(1).tolist(),
            "sides_px": [round(s, 1) for s in sides],
            "px_per_mm_nominal": round(px_per_mm, 4),
            "px_per_mm_affine": [round(sx, 4), round(sy, 4)],
            "anisotropy": round(sy / sx, 4),
            "image_wh": [img.shape[1], img.shape[0]],
        }
        print(
            f"{name:10s} ✅ 边长 {np.mean(sides):6.1f}px "
            f"nominal {px_per_mm:5.2f}px/mm | affine sx={sx:5.2f} sy={sy:5.2f} "
            f"各向异性 {sy / sx:5.3f}"
        )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DETECT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2))


def garment_mask(item: int, img: np.ndarray, origin, ppm: float) -> np.ndarray:
    """按单品设定颜色掩码，排除标定卡区域，取最大连通域。"""
    b = img[:, :, 0].astype(np.int16)
    r = img[:, :, 2].astype(np.int16)
    chroma = img.max(axis=2).astype(np.int16) - img.min(axis=2).astype(np.int16)
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2].astype(np.int16)

    if item == 4:  # 咖色长袖 T：有彩度、偏暖
        raw = (chroma > 28) & (r > b + 12)
    elif item == 11:  # 黑色薄夹克：只看明度
        raw = v < 105
    else:  # 深蓝牛仔裤
        raw = (b > r + 10) & (chroma > 14)

    mask = raw.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))

    # 挖掉标定卡
    x0, y0 = origin
    cx0 = int(max(0, (CARD_BOX_MM[0] - x0) * ppm))
    cy0 = int(max(0, (CARD_BOX_MM[1] - y0) * ppm))
    cx1 = int(min(img.shape[1], (CARD_BOX_MM[2] - x0) * ppm))
    cy1 = int(min(img.shape[0], (CARD_BOX_MM[3] - y0) * ppm))
    if cx1 > cx0 and cy1 > cy0:
        mask[cy0:cy1, cx0:cx1] = 0

    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return np.zeros_like(mask)
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = 1 + int(np.argmax(areas))
    # 最大连通域占全部前景不足 40% → 衣物被打断，退回全部前景
    if areas.max() < 0.40 * areas.sum():
        return mask
    return ((labels == largest).astype(np.uint8)) * 255


def top_extent_px(mask: np.ndarray, ppm: float):
    """上装：以衣领中点为竖轴，量该竖轴上掩码的纵向跨度（像素）。"""
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None
    ytop = int(ys.min())
    band = ys <= ytop + int(10 * ppm)  # 顶部 1cm 决定衣领中点
    xc = int(np.median(xs[band]))
    half = max(2, int(5 * ppm))  # ±5mm 竖轴
    col = mask[:, max(0, xc - half) : xc + half + 1]
    rows = np.where(col.any(axis=1))[0]
    if len(rows) == 0:
        return None
    return int(rows.min()), int(rows.max()), xc


def pants_extent_px(mask: np.ndarray):
    """裤子：最小外接矩形的长边（对轻微旋转免疫）。"""
    ys, xs = np.where(mask > 0)
    if len(ys) == 0:
        return None
    pts = np.column_stack([xs, ys]).astype(np.float32)
    (_, _), (w, h), angle = cv2.minAreaRect(pts)
    return float(max(w, h)), float(min(w, h)), float(angle)


def cmd_rectify(transform: str = "homography") -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, name in PHOTOS.items():
        img = load(PHOTO_DIR / name)
        corners = detect_marker(img)
        if corners is None:
            print(f"{name}: 无标记，跳过")
            continue
        M = marker_homography(corners) if transform == "homography" else marker_affine(corners)
        rect, origin, ppm = rectify(img, M)
        cv2.imwrite(str(OUT_DIR / f"rect_{key}.png"), rect)
        print(f"{name}: rect_{key}.png {rect.shape[1]}x{rect.shape[0]} origin={origin}")


def measure_photo(photo: str, item: int, transform: str):
    info = ITEMS[item]
    img = load(PHOTO_DIR / photo)
    corners = detect_marker(img)
    if corners is None:
        return {"detected": False}
    M = marker_homography(corners) if transform == "homography" else marker_affine(corners)
    sx, sy = affine_scales(marker_affine(corners))
    rect, origin, ppm = rectify(img, M)
    mask = garment_mask(item, rect, origin, ppm)
    if mask.sum() == 0:
        return {"detected": True, "garment": False}

    if info["kind"] == "top":
        ext = top_extent_px(mask, ppm)
        length_cm = (ext[1] - ext[0]) / ppm / 10.0 if ext else None
        detail = {"axis_x_px": ext[2] if ext else None}
    else:
        ext = pants_extent_px(mask)
        length_cm = ext[0] / ppm / 10.0 if ext else None
        detail = {
            "short_side_cm": round(ext[1] / ppm / 10.0, 2) if ext else None,
            "angle_deg": round(ext[2], 1) if ext else None,
        }
    err = round(length_cm - info["truth_cm"], 2) if length_cm is not None else None
    cv2.imwrite(str(OUT_DIR / f"m_{photo.rsplit('.', 1)[0]}.png"), mask)
    return {
        "detected": True,
        "garment": True,
        "length_cm": round(length_cm, 2) if length_cm else None,
        "truth_cm": info["truth_cm"],
        "error_cm": err,
        "marker_px": round(float(np.mean(side_lengths(corners))), 1),
        "anisotropy": round(sy / sx, 4),
        **detail,
    }


def cmd_measure() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    print(f"{'照片':11s}{'单品':8s}{'角度':>5s}  {'仿射':>17s}  {'单应':>17s}")
    for key, name in PHOTOS.items():
        item = int(key.split(".")[0])
        angle = int(key.split(".")[1])
        info = ITEMS[item]
        res = {}
        diag = {}
        for transform in ("affine", "homography"):
            r = measure_photo(name, item, transform)
            if transform == "affine":
                diag = {k: r[k] for k in ("marker_px", "anisotropy") if k in r}
            if r.get("length_cm") is not None:
                res[transform] = r["length_cm"]
        if not res:
            print(f"{name:11s}{info['name']:8s}{angle:3d}°  测量失败")
            rows.append({"photo": name, "item": info["name"], "angle_deg": angle,
                         "truth_cm": info["truth_cm"], "error": "测量失败"})
            continue
        rows.append({
            "photo": name,
            "item": info["name"],
            "angle_deg": angle,
            "truth_cm": info["truth_cm"],
            "length_cm": {k: round(v, 2) for k, v in res.items()},
            "error_cm": {k: round(v - info["truth_cm"], 2) for k, v in res.items()},
            **diag,
        })
        cells = "  ".join(
            f"{res.get(t, float('nan')):6.2f}cm {res.get(t, float('nan')) - info['truth_cm']:+6.2f}"
            for t in ("affine", "homography")
        )
        print(f"{name:11s}{info['name']:8s}{angle:3d}°  {cells}")

    RESULT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\n→ {RESULT_PATH}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["detect", "rectify", "measure"])
    ap.add_argument("--transform", choices=["affine", "homography"], default="homography")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.cmd == "detect":
        cmd_detect()
    elif args.cmd == "rectify":
        cmd_rectify(args.transform)
    else:
        cmd_measure()


if __name__ == "__main__":
    main()
