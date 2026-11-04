"""鞋码回填脚本：参数校验、干跑不写库、只填空值。"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from factories import make_item
from src.db.connection import connect, open_db
from src.db.repo import get_item, insert_item

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "backfill_shoe_sizes", ROOT / "scripts" / "backfill_shoe_sizes.py"
)
assert SPEC and SPEC.loader
backfill = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backfill)


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "wardrobe.db"
    open_db(path).close()
    conn = connect(path)
    try:
        insert_item(conn, make_item(id=1, category="T恤", layers=("inner",)))
        insert_item(conn, make_item(id=15, category="鞋", layers=("shoes",)))
        insert_item(
            conn, make_item(id=16, category="鞋", layers=("shoes",), shoe_size=42.0)
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _size(db_path: Path, item_id: int) -> float | None:
    conn = connect(db_path)
    try:
        item = get_item(conn, item_id)
        assert item is not None
        return item.shoe_size
    finally:
        conn.close()


def test_parse_pairs_accepts_half_sizes() -> None:
    assert backfill.parse_pairs(["15=43", " 16 = 42.5 "]) == {15: 43.0, 16: 42.5}


@pytest.mark.parametrize(
    "raws",
    [
        ["15"],
        ["x=43"],
        ["15=大"],
        ["15=29"],
        ["15=51"],
        ["15=42.3"],
        ["15=43", "15=44"],
    ],
)
def test_parse_pairs_rejects_bad_input(raws) -> None:
    with pytest.raises(ValueError):
        backfill.parse_pairs(raws)


def test_dry_run_does_not_write(db) -> None:
    assert backfill.main(["15=43", "--db", str(db)]) == 0
    assert _size(db, 15) is None


def test_apply_fills_only_empty_sizes(db, capsys) -> None:
    assert backfill.main(["15=43", "16=42", "--db", str(db), "--apply"]) == 0
    assert _size(db, 15) == 43.0
    assert _size(db, 16) == 42.0
    assert "已写入 1 双" in capsys.readouterr().out


def test_apply_is_idempotent(db, capsys) -> None:
    backfill.main(["15=43", "--db", str(db), "--apply"])
    capsys.readouterr()
    assert backfill.main(["15=43", "--db", str(db), "--apply"]) == 0
    assert _size(db, 15) == 43.0
    assert "库已是最新" in capsys.readouterr().out


def test_existing_different_size_is_not_overwritten(db, capsys) -> None:
    assert backfill.main(["16=43", "--db", str(db), "--apply"]) == 1
    assert _size(db, 16) == 42.0
    assert "不覆盖" in capsys.readouterr().err


def test_non_shoe_category_is_rejected(db, capsys) -> None:
    assert backfill.main(["1=43", "--db", str(db), "--apply"]) == 1
    assert "不是鞋" in capsys.readouterr().err


def test_missing_item_is_rejected(db, capsys) -> None:
    assert backfill.main(["99=43", "--db", str(db), "--apply"]) == 1
    assert "不存在" in capsys.readouterr().err


def test_missing_database_is_reported(tmp_path, capsys) -> None:
    missing = tmp_path / "nope.db"
    assert backfill.main(["15=43", "--db", str(missing)]) == 1
    assert "找不到数据库" in capsys.readouterr().err
