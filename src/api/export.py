"""数据导出：数据库快照 + 照片清单。

照片二进制不进入 zip。清单只记录相对路径、字节数与 SHA-256，
路径必须解析到 `pic/` 或照片目录内部；绝对路径、`..`、符号链接逃逸只记
`safe: false`，既不影响导出，也不暴露文件内容。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..db.repo import photo_rows

PHOTO_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
PHOTO_PREFIXES = {
    "pic/": "pic",
    "photos/": "photos",
}


def _resolve_photo(raw: str, roots: dict[str, Path]) -> tuple[Path | None, bool]:
    """返回 (绝对路径, 是否安全)。不安全或不存在都返回 None。"""
    if not isinstance(raw, str) or not raw:
        return None, False
    if raw.startswith("/") or raw.startswith("\\") or ":" in raw.split("/")[0]:
        return None, False
    prefix, _, rest = raw.partition("/")
    kind = PHOTO_PREFIXES.get(f"{prefix}/")
    if kind is None or not rest or ".." in Path(rest).parts:
        return None, False
    root = roots.get(kind)
    if root is None:
        return None, False
    try:
        base = root.resolve()
        candidate = (base / rest).resolve()
    except (OSError, RuntimeError):
        return None, False
    if not candidate.is_relative_to(base):
        return None, False
    return candidate, True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    db_path: str | Path, pic_dir: Path, photo_dir: Path
) -> dict[str, Any]:
    roots = {"pic": pic_dir, "photos": photo_dir}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = photo_rows(conn)
    finally:
        conn.close()

    entries: list[dict[str, Any]] = []
    for row in rows:
        photos = (("photo", row["photo_path"]), ("cutout", row["cutout_path"]))
        photos += tuple(("extra", raw) for raw in row["extra_photos"])
        for kind, raw in photos:
            if not raw:
                continue
            resolved, safe = _resolve_photo(raw, roots)
            exists = bool(resolved and resolved.is_file())
            entries.append(
                {
                    "item_id": row["id"],
                    "name": row["name"],
                    "kind": kind,
                    "path": raw,
                    "safe": safe,
                    "exists": exists,
                    "bytes": resolved.stat().st_size if exists else None,
                    "sha256": _sha256(resolved) if exists else None,
                }
            )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "只含照片清单，不含照片文件本身。path 为相对路径。",
        "photos": entries,
    }


def _readme(manifest: dict[str, Any]) -> str:
    total = len(manifest["photos"])
    present = sum(1 for entry in manifest["photos"] if entry["exists"])
    return (
        "个人穿搭助手 · 数据导出\n"
        "====================\n\n"
        "本压缩包包含：\n"
        "- wardrobe.db：SQLite 一致性快照（属性、地点、身材、反馈）\n"
        "- photos.json：照片清单（相对路径、字节数、SHA-256）\n"
        "- README.txt：本说明\n\n"
        f"照片清单 {total} 条，其中原文件存在 {present} 条。\n"
        "照片文件本身不在压缩包内；原图仍在本机的 pic/ 与 data/photos/。\n"
        "不要用本压缩包替代照片备份。\n"
    )


def build_export_zip(
    db_path: str | Path, pic_dir: Path, photo_dir: Path
) -> bytes:
    """生成 zip 字节。调用方负责设置下载头。"""
    manifest = build_manifest(db_path, pic_dir, photo_dir)
    with tempfile.TemporaryDirectory(prefix="wardrobe-export-") as tmp:
        snapshot = Path(tmp) / "wardrobe.db"
        source = sqlite3.connect(db_path)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

        buffer = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot, "wardrobe.db")
            archive.writestr(
                "photos.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            archive.writestr("README.txt", _readme(manifest))
        buffer.seek(0)
        return buffer.read()


def scan_photo_stats(dirs: list[Path]) -> dict[str, int]:
    """统计照片目录里的普通文件；跳过符号链接与隐藏文件。"""
    seen: set[Path] = set()
    count = 0
    total = 0
    for directory in dirs:
        try:
            root = directory.resolve()
        except (OSError, RuntimeError):
            continue
        if root in seen or not root.is_dir():
            continue
        seen.add(root)
        with os.scandir(root) as entries:
            for entry in entries:
                if entry.name.startswith(".") or entry.is_symlink():
                    continue
                if Path(entry.name).suffix.lower() not in PHOTO_EXTENSIONS:
                    continue
                try:
                    if not entry.is_file():
                        continue
                    count += 1
                    total += entry.stat().st_size
                except OSError:
                    continue
    return {"count": count, "bytes": total}


def db_size(path: str | Path) -> int:
    base = Path(path)
    total = 0
    for candidate in (base, Path(f"{base}-wal"), Path(f"{base}-shm")):
        try:
            if candidate.is_file():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total
