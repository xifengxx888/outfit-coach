#!/usr/bin/env python3
"""把量衣表格导入 SQLite。

用法：
    .venv/bin/python scripts/import_items.py                    # 导入为 draft
    .venv/bin/python scripts/import_items.py --status confirmed # 直接导入为已确认
    .venv/bin/python scripts/import_items.py --update-existing  # 覆盖同 id 的旧行

默认导入为 draft：draft 不参与求解，等 A 视图确认后才会成为求解输入。
重复跑是安全的：已存在的 id 默认跳过，不会重复插入。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.db.connection import DEFAULT_DB_PATH, open_db  # noqa: E402
from src.db.importer import load_rows, parse_rows  # noqa: E402
from src.db.repo import count_by_status, get_item, insert_item, update_item  # noqa: E402

DEFAULT_SOURCE = ROOT / "scripts" / "spike" / "items_template.xlsx"
STATUS_LABEL = {"draft": "草稿", "confirmed": "已确认", "archived": "已淘汰"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入量衣表格到 wardrobe.db")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="量衣表格路径")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 路径")
    parser.add_argument(
        "--status",
        choices=("draft", "confirmed"),
        default="draft",
        help="导入后的状态，默认 draft（不参与求解）",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="同 id 已存在时用表格内容覆盖，默认跳过",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.source.exists():
        print(f"找不到量衣表格：{args.source}", file=sys.stderr)
        return 1

    result = parse_rows(load_rows(args.source), default_status=args.status)
    if not result.items:
        print("没有解析出任何单品，请检查表格", file=sys.stderr)
        return 1

    conn = open_db(args.db)
    inserted = updated = skipped = 0
    try:
        for item in result.items:
            existing = get_item(conn, item.id)
            if existing is None:
                insert_item(conn, item)
                inserted += 1
            elif args.update_existing:
                update_item(conn, item)
                updated += 1
            else:
                skipped += 1
                print(f"跳过已有单品 #{item.id} {item.name}（加 --update-existing 可覆盖）")
        conn.commit()
        status_counts = count_by_status(conn)
    finally:
        conn.close()

    missing_photos = [
        item.photo_path
        for item in result.items
        if item.photo_path and not (ROOT / item.photo_path).exists()
    ]

    print()
    print(f"解析 {len(result.items)} 件：新增 {inserted}，更新 {updated}，跳过 {skipped}")
    for status, count in status_counts.items():
        print(f"库内{STATUS_LABEL.get(status, status)}：{count} 件")
    if args.status == "draft":
        print("注意：draft 单品不参与求解，确认后再进入每日建议。")
    if missing_photos:
        print(f"照片缺失 {len(missing_photos)} 个：{', '.join(missing_photos[:5])}"
              + (" …" if len(missing_photos) > 5 else ""))
    if result.warnings:
        print(f"跳过/忽略 {len(result.warnings)} 处：")
        for warning in result.warnings:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
