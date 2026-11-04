"""M1 数据层：连接、建表、仓储、表格导入。"""

from __future__ import annotations

from .connection import DEFAULT_DB_PATH, SCHEMA_PATH, connect, init_db, open_db
from .importer import ParseResult, load_rows, parse_rows
from .repo import (
    FEEDBACK_SIGNALS,
    ITEM_WRITE_COLUMNS,
    backfill_ignored_suggestions,
    count_by_status,
    delete_daily_suggestion,
    get_item,
    has_feedback_on,
    insert_item,
    item_params,
    load_feedback,
    load_items,
    load_recent_swaps,
    load_stale_daily_suggestions,
    outfit_hash,
    record_feedback,
    update_item,
    upsert_daily_suggestion,
)

__all__ = [
    "DEFAULT_DB_PATH",
    "SCHEMA_PATH",
    "FEEDBACK_SIGNALS",
    "ITEM_WRITE_COLUMNS",
    "ParseResult",
    "backfill_ignored_suggestions",
    "connect",
    "count_by_status",
    "delete_daily_suggestion",
    "get_item",
    "has_feedback_on",
    "init_db",
    "insert_item",
    "item_params",
    "load_feedback",
    "load_items",
    "load_recent_swaps",
    "load_stale_daily_suggestions",
    "load_rows",
    "open_db",
    "outfit_hash",
    "parse_rows",
    "record_feedback",
    "update_item",
    "upsert_daily_suggestion",
]
