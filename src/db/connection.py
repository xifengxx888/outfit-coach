"""SQLite 连接与建表。

这里只负责「打开连接 + 建表」，业务查询在 `repo.py`。
默认库文件是 `data/db/wardrobe.db`，与 `CLAUDE.md` 的目录约定一致。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = ROOT / "data" / "db" / "wardrobe.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """打开数据库。行按列名访问，外键约束打开。

    文件库用 WAL 模式；内存库（测试用）跳过 WAL——内存库不支持。
    """
    is_memory = str(db_path) == ":memory:"
    if not is_memory:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not is_memory:
        conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """按 `schema.sql` 建表，再给老库补齐后加的列。

    全部语句都是幂等的，可重复跑。
    """
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _ensure_item_columns(conn)
    conn.commit()


# 后加的列。老库只有 photo_path，新库在 schema.sql 里已带 CHECK；
# ALTER TABLE 只补「列存在性」，重复执行无副作用，不改任何已有行。
_ITEM_COLUMNS = {
    "extra_photos": "TEXT NOT NULL DEFAULT '[]'",
    "shoe_size": "REAL",
}


def _ensure_item_columns(conn: sqlite3.Connection) -> None:
    # PRAGMA table_info 的第 2 列是列名；用下标访问，不依赖 row_factory
    have = {row[1] for row in conn.execute("PRAGMA table_info(item)")}
    for name, ddl in _ITEM_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE item ADD COLUMN {name} {ddl}")


def open_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """连接并确保表已建好，脚本入口用。"""
    conn = connect(db_path)
    init_db(conn)
    return conn
