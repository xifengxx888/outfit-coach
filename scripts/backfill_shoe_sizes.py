#!/usr/bin/env python3
"""给鞋类单品补 EU 鞋码。

只填空值：已有尺码的不覆盖（要改请在页面编辑）。默认干跑。

用法：
    .venv/bin/python scripts/backfill_shoe_sizes.py 15=43 16=42.5
    .venv/bin/python scripts/backfill_shoe_sizes.py 15=43 16=42.5 --apply
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.api.schemas import SHOE_CATEGORIES  # noqa: E402
from src.db.connection import DEFAULT_DB_PATH, open_db  # noqa: E402
from src.db.repo import get_item, load_items, update_item  # noqa: E402

MIN_SIZE = 30.0
MAX_SIZE = 50.0


def parse_pairs(raws: list[str]) -> dict[int, float]:
    """把 `15=43` 解析成 {15: 43.0}。任何一项不合法就整体报错。"""
    pairs: dict[int, float] = {}
    for raw in raws:
        text = raw.strip()
        if "=" not in text:
            raise ValueError(f"格式应为 <id>=<码>：{raw}")
        left, right = text.split("=", 1)
        try:
            item_id = int(left)
            size = float(right)
        except ValueError:
            raise ValueError(f"格式应为 <id>=<码>：{raw}") from None
        if not MIN_SIZE <= size <= MAX_SIZE:
            raise ValueError(f"鞋码超出 {MIN_SIZE:g}–{MAX_SIZE:g}：{raw}")
        if round(size * 2) != size * 2:
            raise ValueError(f"鞋码必须按 0.5 递增：{raw}")
        if item_id in pairs and pairs[item_id] != size:
            raise ValueError(f"同一件给了两个不同的码：{item_id}")
        pairs[item_id] = size
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="给鞋类单品补 EU 鞋码")
    parser.add_argument("pairs", nargs="+", metavar="ID=码", help="如 15=43 16=42.5")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 路径")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="真正写库；不加时只打印将要发生的改动",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pairs = parse_pairs(args.pairs)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not args.db.exists():
        print(f"找不到数据库：{args.db}", file=sys.stderr)
        return 1

    conn = open_db(args.db)
    problems: list[str] = []
    changes: list[tuple[int, str, float]] = []
    try:
        for item_id, size in sorted(pairs.items()):
            item = get_item(conn, item_id)
            if item is None:
                problems.append(f"#{item_id} 不存在")
                continue
            if item.category not in SHOE_CATEGORIES:
                problems.append(f"#{item_id} 不是鞋（品类：{item.category}）")
                continue
            if item.shoe_size == size:
                continue
            if item.shoe_size is not None:
                problems.append(f"#{item_id} 已有鞋码 {item.shoe_size:g}，不覆盖")
                continue
            changes.append((item_id, item.name, size))

        if problems:
            print("发现问题，未写库：", file=sys.stderr)
            for problem in problems:
                print(f"  ✗ {problem}", file=sys.stderr)
            return 1

        for item_id, name, size in changes:
            print(f"#{item_id} {name} → {size:g} 码")

        if not changes:
            print("没有需要填写的鞋码，库已是最新。")
        elif not args.apply:
            print(f"\n干跑结束：{len(changes)} 双待更新，未写库。加 --apply 执行。")

        if args.apply and changes:
            for item_id, _, size in changes:
                item = get_item(conn, item_id)
                if item is None or item.shoe_size is not None:  # 打印后库被改动，保守跳过
                    continue
                update_item(conn, replace(item, shoe_size=size))
            conn.commit()
            print(f"\n已写入 {len(changes)} 双。")

        missing = [
            f"#{item.id} {item.name}"
            for item in load_items(conn, statuses=None)
            if item.category in SHOE_CATEGORIES and item.shoe_size is None
        ]
        if missing:
            print("仍缺鞋码：" + "、".join(missing))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
