"""仓储层：单品与反馈的读写。

所有值都走参数绑定；SQL 里的列名只来自本模块的常量，不拼接任何外部输入。
`Item` 与表字段一一对应，`layers` / `seasons` / `hit_rules` 在库里是 JSON 文本，
在 Python 侧是 tuple。

色彩派生列（hue_family / lightness / saturation / warmth）每次写库时由 `color_hex`
重算。规则引擎不读这几列，它们只服务查询与展示，因此不会与规则判定产生第二套口径。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ..rules.color_math import color_attrs
from ..rules.identity import outfit_hash
from ..rules.types import Item

# 写库字段。created_at 交给数据库默认值，不在这里维护。
ITEM_WRITE_COLUMNS = (
    "id",
    "name",
    "photo_path",
    "extra_photos",
    "cutout_path",
    "category",
    "layers",
    "formality",
    "color_hex",
    "hue_family",
    "lightness",
    "saturation",
    "warmth",
    "fit",
    "pattern",
    "collar",
    "material",
    "weight",
    "length_cm",
    "shoulder_cm",
    "chest_width_cm",
    "sleeve_cm",
    "waist_cm",
    "hip_cm",
    "leg_opening_cm",
    "shoe_size",
    "seasons",
    "status",
    "source",
    "last_worn_at",
)

_INSERT_SQL = (
    f"INSERT INTO item ({', '.join(ITEM_WRITE_COLUMNS)}) "
    f"VALUES ({', '.join(':' + c for c in ITEM_WRITE_COLUMNS)})"
)
_UPDATE_SQL = (
    "UPDATE item SET "
    + ", ".join(f"{c} = :{c}" for c in ITEM_WRITE_COLUMNS if c != "id")
    + " WHERE id = :id"
)


def _to_json(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=False)


def _from_json(text: str) -> tuple[str, ...]:
    return tuple(json.loads(text))


def item_params(item: Item) -> dict[str, Any]:
    """把 `Item` 摊成写库参数字典，顺带算好色彩派生列。"""
    attrs = color_attrs(item.color_hex)
    return {
        "id": item.id,
        "name": item.name,
        "photo_path": item.photo_path,
        "extra_photos": _to_json(item.extra_photos),
        "cutout_path": item.cutout_path,
        "category": item.category,
        "layers": _to_json(item.layers),
        "formality": item.formality,
        "color_hex": item.color_hex,
        "hue_family": attrs.hue_family,
        "lightness": round(attrs.lightness, 2),
        "saturation": round(attrs.saturation, 2),
        "warmth": attrs.warmth,
        "fit": item.fit,
        "pattern": item.pattern,
        "collar": item.collar,
        "material": item.material,
        "weight": item.weight,
        "length_cm": item.length_cm,
        "shoulder_cm": item.shoulder_cm,
        "chest_width_cm": item.chest_width_cm,
        "sleeve_cm": item.sleeve_cm,
        "waist_cm": item.waist_cm,
        "hip_cm": item.hip_cm,
        "leg_opening_cm": item.leg_opening_cm,
        "shoe_size": item.shoe_size,
        "seasons": _to_json(item.seasons),
        "status": item.status,
        "source": item.source,
        "last_worn_at": item.last_worn_at,
    }


def _row_to_item(row: sqlite3.Row) -> Item:
    return Item(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        layers=_from_json(row["layers"]),
        formality=row["formality"],
        color_hex=row["color_hex"],
        fit=row["fit"],
        pattern=row["pattern"],
        weight=row["weight"],
        material=row["material"],
        collar=row["collar"],
        length_cm=row["length_cm"],
        shoulder_cm=row["shoulder_cm"],
        chest_width_cm=row["chest_width_cm"],
        sleeve_cm=row["sleeve_cm"],
        waist_cm=row["waist_cm"],
        hip_cm=row["hip_cm"],
        leg_opening_cm=row["leg_opening_cm"],
        extra_photos=_from_json(row["extra_photos"] or "[]"),
        shoe_size=row["shoe_size"],
        seasons=_from_json(row["seasons"]),
        photo_path=row["photo_path"],
        cutout_path=row["cutout_path"],
        status=row["status"],
        source=row["source"],
        last_worn_at=row["last_worn_at"],
    )


# ---------------------------------------------------------------------------
# 单品
# ---------------------------------------------------------------------------


def next_item_id(conn: sqlite3.Connection) -> int:
    """分配下一个单品 id。单用户本地库，取号与插入放在同一事务里即可。"""
    row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM item").fetchone()
    return int(row[0])


def insert_item(conn: sqlite3.Connection, item: Item) -> None:
    """插入单品。id 冲突会抛 `sqlite3.IntegrityError`，由调用方决定是否更新。"""
    conn.execute(_INSERT_SQL, item_params(item))


def update_item(conn: sqlite3.Connection, item: Item) -> int:
    """按 id 覆盖可写字段，返回受影响行数（0 表示该 id 不存在）。"""
    return conn.execute(_UPDATE_SQL, item_params(item)).rowcount


def get_item(conn: sqlite3.Connection, item_id: int) -> Item | None:
    row = conn.execute("SELECT * FROM item WHERE id = ?", (item_id,)).fetchone()
    return _row_to_item(row) if row else None


def load_items(
    conn: sqlite3.Connection,
    statuses: Sequence[str] | None = ("confirmed",),
) -> list[Item]:
    """按状态读单品。

    `statuses` 默认只读 confirmed——draft 还没经 A 视图确认，archived 已淘汰，
    两者都不该进入求解。传 `None` 读全部（诊断、导出用）。
    """
    if statuses is None:
        rows = conn.execute("SELECT * FROM item ORDER BY id").fetchall()
    else:
        if not statuses:
            return []
        marks = ", ".join("?" for _ in statuses)
        rows = conn.execute(
            f"SELECT * FROM item WHERE status IN ({marks}) ORDER BY id",
            tuple(statuses),
        ).fetchall()
    return [_row_to_item(row) for row in rows]


def count_by_status(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n FROM item GROUP BY status ORDER BY status"
    ).fetchall()
    return {row["status"]: row["n"] for row in rows}


# ---------------------------------------------------------------------------
# 反馈
# ---------------------------------------------------------------------------

FEEDBACK_SIGNALS = ("adopt", "favorite", "swap", "veto_item", "ignore")


def record_feedback(
    conn: sqlite3.Connection,
    outfit_hash_value: str,
    signal: str,
    *,
    garment_id: int | None = None,
    hit_rules: Iterable[str] = (),
) -> int:
    """记一条反馈，返回自增 id。

    `garment_id` 只有 veto_item 允许且必须给；其余信号给了会被 CHECK 拒绝。
    """
    cur = conn.execute(
        "INSERT INTO feedback (outfit_hash, signal, garment_id, hit_rules) "
        "VALUES (?, ?, ?, ?)",
        (outfit_hash_value, signal, garment_id, _to_json(hit_rules)),
    )
    return int(cur.lastrowid)


def load_feedback(
    conn: sqlite3.Connection, outfit_hash_value: str
) -> list[Mapping[str, Any]]:
    rows = conn.execute(
        "SELECT signal, garment_id, hit_rules, created_at FROM feedback "
        "WHERE outfit_hash = ? ORDER BY id",
        (outfit_hash_value,),
    ).fetchall()
    return [
        {
            "signal": row["signal"],
            "garment_id": row["garment_id"],
            "hit_rules": list(_from_json(row["hit_rules"])),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def load_recent_swaps(
    conn: sqlite3.Connection, days: int = 14
) -> list[tuple[str, str]]:
    """近 N 天被「再换」划过的组合，返回 (本地日期, hash)。

    `created_at` 存的是 UTC，转本地日期放在 SQL 里做，避免 Python 侧
    再维护一套时区口径。
    """
    rows = conn.execute(
        "SELECT date(created_at, 'localtime') AS day, outfit_hash FROM feedback "
        "WHERE signal = 'swap' AND created_at >= datetime('now', ?) "
        "ORDER BY created_at DESC",
        (f"-{int(days)} days",),
    ).fetchall()
    return [(row["day"], row["outfit_hash"]) for row in rows]


# ---------------------------------------------------------------------------
# 每日建议
# ---------------------------------------------------------------------------


def upsert_daily_suggestion(
    conn: sqlite3.Connection,
    day: str,
    outfit_hash_value: str,
    garment_ids: Iterable[int],
    hit_rules: Iterable[str] = (),
) -> None:
    """记下当天最后展示的组合；同一天再次调用时覆盖。"""
    conn.execute(
        "INSERT INTO daily_suggestion (day, outfit_hash, garment_ids, hit_rules) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(day) DO UPDATE SET "
        "outfit_hash = excluded.outfit_hash, "
        "garment_ids = excluded.garment_ids, "
        "hit_rules = excluded.hit_rules, "
        "created_at = datetime('now')",
        (
            day,
            outfit_hash_value,
            _to_json(garment_ids),
            _to_json(hit_rules),
        ),
    )


def load_stale_daily_suggestions(
    conn: sqlite3.Connection, before_day: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT day, outfit_hash, garment_ids, hit_rules FROM daily_suggestion "
        "WHERE day < ? ORDER BY day",
        (before_day,),
    ).fetchall()
    return [
        {
            "day": row["day"],
            "outfit_hash": row["outfit_hash"],
            "garment_ids": list(_from_json(row["garment_ids"])),
            "hit_rules": list(_from_json(row["hit_rules"])),
        }
        for row in rows
    ]


def has_feedback_on(conn: sqlite3.Connection, outfit_hash_value: str, day: str) -> bool:
    """该组合在指定本地日期有没有收到过任何反馈。"""
    row = conn.execute(
        "SELECT 1 FROM feedback WHERE outfit_hash = ? "
        "AND date(created_at, 'localtime') = ? LIMIT 1",
        (outfit_hash_value, day),
    ).fetchone()
    return row is not None


def delete_daily_suggestion(conn: sqlite3.Connection, day: str) -> None:
    conn.execute("DELETE FROM daily_suggestion WHERE day = ?", (day,))


def backfill_ignored_suggestions(
    conn: sqlite3.Connection, before_day: str
) -> int:
    """把更早展示过、当天没有任何反馈的建议补记为 ignore，返回条数。

    处理完即删除该行，保证同一条建议只会被补记一次。
    """
    ignored = 0
    for row in load_stale_daily_suggestions(conn, before_day):
        if not has_feedback_on(conn, row["outfit_hash"], row["day"]):
            record_feedback(
                conn,
                row["outfit_hash"],
                "ignore",
                hit_rules=row["hit_rules"],
            )
            ignored += 1
        delete_daily_suggestion(conn, row["day"])
    return ignored


# ---------------------------------------------------------------------------
# 身材与地点
# ---------------------------------------------------------------------------

PROFILE_FIELDS = (
    "height",
    "weight",
    "shoulder_width",
    "chest",
    "waist",
    "hip",
    "neck",
    "inseam",
    "arm_length",
)
PROFILE_SOURCES = ("body", "garment", "estimated")


def get_profile(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """读单行身材表；没有记录返回 None。"""
    row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        return None
    return {
        "values": {field: row[field] for field in PROFILE_FIELDS},
        "sources": {field: row[f"{field}_source"] for field in PROFILE_FIELDS},
        "updated_at": row["updated_at"],
    }


def profile_height(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT height FROM profile WHERE id = 1").fetchone()
    return int(row["height"]) if row and row["height"] is not None else None


def ensure_profile(conn: sqlite3.Connection) -> None:
    """首次跳过设置时放一行空 profile；已有记录不动。"""
    conn.execute("INSERT INTO profile (id) VALUES (1) ON CONFLICT(id) DO NOTHING")


def upsert_profile(
    conn: sqlite3.Connection,
    values: Mapping[str, int | None],
    sources: Mapping[str, str | None],
) -> None:
    """全量写九项身材与来源。缺省项写 NULL。"""
    columns = PROFILE_FIELDS + tuple(f"{field}_source" for field in PROFILE_FIELDS)
    params: dict[str, Any] = {"id": 1}
    for field in PROFILE_FIELDS:
        params[field] = values.get(field)
        params[f"{field}_source"] = sources.get(field)
    placeholders = ", ".join(":" + column for column in columns)
    updates = ", ".join(
        f"{column} = excluded.{column}" for column in columns if column != "id"
    )
    conn.execute(
        f"INSERT INTO profile (id, {', '.join(columns)}) VALUES (:id, {placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}, updated_at = datetime('now')",
        params,
    )


def get_location(conn: sqlite3.Connection, location_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM location WHERE id = ?", (location_id,)
    ).fetchone()
    return dict(row) if row else None


def list_locations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT l.*, "
        "(SELECT COUNT(*) FROM climate_profile c WHERE c.location_id = l.id) "
        "AS climate_rows "
        "FROM location l ORDER BY l.is_default DESC, l.id"
    ).fetchall()
    return [dict(row) for row in rows]


def count_locations(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM location").fetchone()
    return int(row[0])


def insert_location(
    conn: sqlite3.Connection,
    name: str,
    lat: float,
    lon: float,
    *,
    is_default: bool,
) -> int:
    cursor = conn.execute(
        "INSERT INTO location (name, lat, lon, is_default) VALUES (?, ?, ?, ?)",
        (name, lat, lon, 1 if is_default else 0),
    )
    return int(cursor.lastrowid)


def set_default_location(conn: sqlite3.Connection, location_id: int) -> bool:
    """切换默认地点。返回 False 表示 id 不存在，且不改变现有默认。"""
    exists = conn.execute(
        "SELECT 1 FROM location WHERE id = ?", (location_id,)
    ).fetchone()
    if exists is None:
        return False
    # 唯一部分索引只允许一个 1，必须先清后设
    conn.execute("UPDATE location SET is_default = 0 WHERE is_default = 1")
    conn.execute("UPDATE location SET is_default = 1 WHERE id = ?", (location_id,))
    return True


def upsert_climate(
    conn: sqlite3.Connection,
    location_id: int,
    values: Mapping[tuple[int, int], float],
) -> int:
    """写全年曲线；同一天重复抓取时覆盖。返回写入行数。"""
    rows = [
        (location_id, month, day, temp_avg)
        for (month, day), temp_avg in sorted(values.items())
    ]
    conn.executemany(
        "INSERT INTO climate_profile (location_id, month, day, temp_avg) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(location_id, month, day) DO UPDATE SET "
        "temp_avg = excluded.temp_avg, fetched_at = datetime('now')",
        rows,
    )
    return len(rows)


def load_climate(
    conn: sqlite3.Connection, location_id: int
) -> dict[tuple[int, int], float]:
    rows = conn.execute(
        "SELECT month, day, temp_avg FROM climate_profile WHERE location_id = ?",
        (location_id,),
    ).fetchall()
    return {(int(row["month"]), int(row["day"])): float(row["temp_avg"]) for row in rows}


def count_climate(conn: sqlite3.Connection, location_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM climate_profile WHERE location_id = ?",
        (location_id,),
    ).fetchone()
    return int(row[0])


def photo_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """导出清单用：只取照片相对路径，不读文件。"""
    rows = conn.execute(
        "SELECT id, name, photo_path, extra_photos, cutout_path FROM item ORDER BY id"
    ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "photo_path": row["photo_path"],
            "extra_photos": list(_from_json(row["extra_photos"] or "[]")),
            "cutout_path": row["cutout_path"],
        }
        for row in rows
    ]
