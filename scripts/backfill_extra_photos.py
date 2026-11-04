#!/usr/bin/env python3
"""给已有单品追加多角度照片。

只追加：不删除、不移动、不替换封面，也不改 `photo_path`。
映射写死在本脚本里，重复跑是安全的（已存在的路径跳过）。

用法：
    .venv/bin/python scripts/backfill_extra_photos.py           # 干跑，只打印
    .venv/bin/python scripts/backfill_extra_photos.py --apply   # 写库
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.schemas import MAX_PHOTOS  # noqa: E402
from src.db.connection import DEFAULT_DB_PATH, open_db  # noqa: E402
from src.db.repo import get_item, load_items, update_item  # noqa: E402

PIC_DIR = ROOT / "pic"

# 只收角度明确属于该件的图。16.jpg / 18.jpg 归属不明，不猜、不入库。
PLAN = {
    15: ("pic/15.2.jpg",),
    16: ("pic/16.1.jpg", "pic/16.2.jpg", "pic/16.4.jpg"),
    17: ("pic/17.1.jpg", "pic/17.2.jpg"),
    18: ("pic/18.2.jpg", "pic/18.3.jpg"),
}
UNATTRIBUTED = ("pic/16.jpg", "pic/18.jpg")


def _path_problem(raw: str) -> str | None:
    path = (ROOT / raw).resolve()
    if not path.is_relative_to(PIC_DIR.resolve()):
        return f"路径不在 pic/ 内：{raw}"
    if not path.is_file():
        return f"文件不存在：{raw}"
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="给已有单品追加多角度照片")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 路径")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库；不加时只打印将要发生的改动",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.db.exists():
        print(f"找不到数据库：{args.db}", file=sys.stderr)
        return 1

    conn = open_db(args.db)
    problems: list[str] = []
    changes: list[tuple[int, str, tuple[str, ...], tuple[str, ...]]] = []
    try:
        for item_id, candidates in PLAN.items():
            item = get_item(conn, item_id)
            if item is None:
                problems.append(f"#{item_id} 不存在")
                continue

            add: list[str] = []
            for raw in candidates:
                problem = _path_problem(raw)
                if problem:
                    problems.append(f"#{item_id} {problem}")
                    continue
                if raw == item.photo_path or raw in item.extra_photos:
                    continue
                add.append(raw)

            if not add:
                continue
            if len(item.photos) + len(add) > MAX_PHOTOS:
                problems.append(
                    f"#{item_id} 追加后会超过 {MAX_PHOTOS} 张，未做改动"
                )
                continue
            changes.append((item_id, item.name, item.photos, tuple(add)))

        if problems:
            print("发现问题，未写库：", file=sys.stderr)
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            return 1

        for item_id, name, existing, add in changes:
            print(f"#{item_id} {name}")
            if existing:
                print(f"  已有：{', '.join(existing)}")
            else:
                print("  已有：无照片")
            for raw in add:
                print(f"  + {raw}")

        if not changes:
            print("没有需要追加的照片，库已是最新。")
        elif not args.apply:
            print(f"\n干跑结束：{len(changes)} 件待更新，未写库。加 --apply 执行。")

        if args.apply and changes:
            for item_id, _, _, add in changes:
                item = get_item(conn, item_id)
                if item is None:  # 打印后库被改动，保守跳过
                    continue
                update_item(conn, replace(item, extra_photos=item.extra_photos + add))
            conn.commit()
            print(f"\n已写入 {len(changes)} 件。")

        referenced = {
            path for item in load_items(conn, statuses=None) for path in item.photos
        }
        loose = [
            raw
            for raw in UNATTRIBUTED
            if (ROOT / raw).is_file() and raw not in referenced
        ]
        if loose:
            print("未归属、未入库的图片：" + "、".join(loose))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
