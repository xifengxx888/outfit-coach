"""数据库层单测：建表、Item 往返、派生列、反馈约束与唯一索引。"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from factories import make_item
from src.db.connection import connect, init_db
from src.db.repo import (
    count_by_status,
    get_item,
    insert_item,
    load_feedback,
    load_items,
    outfit_hash,
    record_feedback,
    update_item,
)
from src.rules.color_math import color_attrs

TABLE_NAMES = {"item", "profile", "location", "climate_profile", "feedback"}


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = connect(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def test_schema_creates_the_five_tables(conn: sqlite3.Connection) -> None:
    names = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert TABLE_NAMES <= names


def test_item_roundtrip(conn: sqlite3.Connection) -> None:
    item = make_item(
        layers=("inner", "mid"),
        seasons=("summer", "winter"),
        photo_path="pic/1.jpg",
    )
    insert_item(conn, item)

    loaded = load_items(conn)
    assert loaded == [item]
    assert loaded[0].layers == ("inner", "mid")
    assert loaded[0].seasons == ("summer", "winter")
    assert loaded[0].photo_path == "pic/1.jpg"


def test_photos_and_shoe_size_roundtrip(conn: sqlite3.Connection) -> None:
    item = make_item(
        category="鞋",
        layers=("shoes",),
        photo_path="photos/cover.jpg",
        extra_photos=("photos/a.jpg", "photos/b.jpg"),
        shoe_size=42.5,
    )
    insert_item(conn, item)

    loaded = get_item(conn, 1)
    assert loaded == item
    assert loaded.shoe_size == 42.5
    assert loaded.extra_photos == ("photos/a.jpg", "photos/b.jpg")
    assert loaded.photos == (
        "photos/cover.jpg",
        "photos/a.jpg",
        "photos/b.jpg",
    )


def test_photos_without_cover_still_returns_extras(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(photo_path=None, extra_photos=("photos/a.jpg",)))
    loaded = get_item(conn, 1)
    assert loaded is not None
    assert loaded.photos == ("photos/a.jpg",)


def test_init_db_adds_new_item_columns_to_old_database(tmp_path) -> None:
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.executescript(
        """
        CREATE TABLE item (
            id           INTEGER PRIMARY KEY,
            name         TEXT NOT NULL,
            category     TEXT NOT NULL DEFAULT 'T恤',
            status       TEXT NOT NULL DEFAULT 'confirmed',
            last_worn_at TEXT
        );
        INSERT INTO item (id, name) VALUES (1, '旧衣服');
        """
    )
    raw.commit()
    raw.close()

    conn = connect(path)
    init_db(conn)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(item)")}
    assert {"extra_photos", "shoe_size"} <= columns

    row = conn.execute(
        "SELECT name, extra_photos, shoe_size FROM item WHERE id = 1"
    ).fetchone()
    assert row["name"] == "旧衣服"
    assert row["extra_photos"] == "[]"
    assert row["shoe_size"] is None

    init_db(conn)  # 重复执行不应重复加列或报错
    assert {r["name"] for r in conn.execute("PRAGMA table_info(item)")} == columns
    conn.close()


def test_draft_items_do_not_enter_solving_input(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=1, name="已确认"))
    insert_item(conn, make_item(id=2, name="草稿", status="draft"))

    assert [item.id for item in load_items(conn)] == [1]
    assert [item.id for item in load_items(conn, statuses=None)] == [1, 2]
    assert count_by_status(conn) == {"confirmed": 1, "draft": 1}


def test_derived_color_columns_are_written_from_hex(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(color_hex="#1F3A5F"))
    row = conn.execute(
        "SELECT hue_family, lightness, saturation, warmth FROM item WHERE id = 1"
    ).fetchone()
    attrs = color_attrs("#1F3A5F")

    assert row["hue_family"] == attrs.hue_family == "蓝"
    assert row["warmth"] == attrs.warmth == "neutral"
    assert row["lightness"] == pytest.approx(attrs.lightness, abs=0.01)
    assert row["saturation"] == pytest.approx(attrs.saturation, abs=0.01)


def test_duplicate_id_is_rejected(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=7))
    with pytest.raises(sqlite3.IntegrityError):
        insert_item(conn, make_item(id=7, name="另一件"))


def test_update_item_overwrites_writable_fields(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=7, name="旧名字", status="draft"))
    changed = make_item(id=7, name="新名字", status="confirmed")
    assert update_item(conn, changed) == 1

    loaded = get_item(conn, 7)
    assert loaded is not None
    assert loaded.name == "新名字"
    assert loaded.status == "confirmed"


def test_update_missing_item_reports_zero(conn: sqlite3.Connection) -> None:
    assert update_item(conn, make_item(id=99)) == 0


def test_bad_hex_is_rejected_by_check(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=1))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE item SET color_hex = '#ZZZZZZ' WHERE id = 1")


def test_outfit_hash_is_order_independent_and_stable() -> None:
    expected = hashlib.sha1("1,2,3".encode()).hexdigest()[:16]
    assert outfit_hash([3, 1, 2]) == expected
    assert outfit_hash([1, 2, 3, 2]) == expected
    assert len(outfit_hash([1])) == 16


def test_feedback_roundtrip(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=1))
    hash_value = outfit_hash([1])
    feedback_id = record_feedback(conn, hash_value, "adopt", hit_rules=["R-COL-01"])

    assert feedback_id == 1
    rows = load_feedback(conn, hash_value)
    assert rows[0]["signal"] == "adopt"
    assert rows[0]["garment_id"] is None
    assert rows[0]["hit_rules"] == ["R-COL-01"]


def test_veto_item_requires_a_garment(conn: sqlite3.Connection) -> None:
    insert_item(conn, make_item(id=1))
    with pytest.raises(sqlite3.IntegrityError):
        record_feedback(conn, outfit_hash([1]), "veto_item")
    with pytest.raises(sqlite3.IntegrityError):
        record_feedback(conn, outfit_hash([1]), "adopt", garment_id=1)

    record_feedback(conn, outfit_hash([1]), "veto_item", garment_id=1)
    assert load_feedback(conn, outfit_hash([1]))[0]["garment_id"] == 1


def test_unknown_feedback_signal_is_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        record_feedback(conn, outfit_hash([1]), "love")


def test_only_one_default_location(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO location (name, lat, lon, is_default) VALUES ('家', 30.0, 120.0, 1)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO location (name, lat, lon, is_default) "
            "VALUES ('公司', 30.1, 120.1, 1)"
        )
    # 非默认地点可以有多个
    conn.execute(
        "INSERT INTO location (name, lat, lon, is_default) VALUES ('公司', 30.1, 120.1, 0)"
    )
    assert conn.execute("SELECT COUNT(*) FROM location").fetchone()[0] == 2


def test_climate_profile_is_unique_per_day(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO location (id, name, lat, lon) VALUES (1, '家', 30.0, 120.0)"
    )
    conn.execute(
        "INSERT INTO climate_profile (location_id, month, day, temp_avg) "
        "VALUES (1, 10, 26, 18.5)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO climate_profile (location_id, month, day, temp_avg) "
            "VALUES (1, 10, 26, 19.0)"
        )
