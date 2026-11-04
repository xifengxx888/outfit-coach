"""照片落盘：把客户端压缩后的 data URL 变成一张干净的 JPEG。

M1 不接 multipart，照片随 JSON 上传。客户端已经压到最长边 1600，
这里做的是不信任客户端的二次校验：真图、格式白名单、像素上限。
重新编码 JPEG 会天然剥掉 EXIF/GPS，方向由 `exif_transpose` 先转正。

任何失败都抛 `PhotoError`，消息直接给用户看，不含路径与堆栈。
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import secrets
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

# 编码串上限：12M 字符 ≈ 9MB 原图，客户端压过之后远小于此
MAX_DATA_URL_CHARS = 12 * 1024 * 1024
MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 1600
JPEG_QUALITY = 85
ALLOWED_MIME = ("image/jpeg", "image/png", "image/webp")

_BAD_FORMAT = "照片格式不对，请重新选择图片"
_TOO_BIG = "照片太大，请重新拍摄或在相册里压缩后再选"
_UNREADABLE = "这张图读不出来，请换成 JPG 再试"


class PhotoError(ValueError):
    """照片不可用。"""


def _decode(data_url: str) -> bytes:
    if not isinstance(data_url, str) or not data_url.startswith("data:"):
        raise PhotoError(_BAD_FORMAT)
    header, sep, payload = data_url.partition(",")
    if not sep or not header.endswith(";base64"):
        raise PhotoError(_BAD_FORMAT)
    mime = header[5:-7].lower()
    if mime not in ALLOWED_MIME:
        raise PhotoError("只支持 JPG / PNG / WebP 图片")
    if len(payload) > MAX_DATA_URL_CHARS:
        raise PhotoError(_TOO_BIG)
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        raise PhotoError("照片数据损坏，请重新拍摄") from None
    if not raw:
        raise PhotoError("照片数据为空，请重新拍摄")
    if len(raw) > MAX_BYTES:
        raise PhotoError(_TOO_BIG)
    return raw


def _to_rgb(img: Image.Image) -> Image.Image:
    """带透明通道的图铺白底，其余直接转 RGB。"""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.getchannel("A"))
        return canvas
    return img.convert("RGB")


def _prepare(raw: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            width, height = probe.size
            # 先按声明尺寸拦解压炸弹，再解码
            if width * height > MAX_PIXELS:
                raise PhotoError("照片分辨率太高，请压缩后再试")
            probe.load()
            upright = ImageOps.exif_transpose(probe)
            rgb = _to_rgb(upright)
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError(_UNREADABLE) from None
    rgb.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    return rgb


def save_photo(data_url: str, target_dir: str | Path) -> str:
    """校验并写入 `<target_dir>/<随机名>.jpg`，返回库里的相对路径 `photos/<名>.jpg`。"""
    rgb = _prepare(_decode(data_url))

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.jpg"
    tmp = target / f".{name}.tmp"
    try:
        rgb.save(tmp, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        os.replace(tmp, target / name)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise PhotoError("照片保存失败，请稍后重试") from None
    return f"photos/{name}"


__all__ = ["PhotoError", "save_photo"]
