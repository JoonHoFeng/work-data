#!/usr/bin/env python3
"""SQLite data layer for the lightweight worklog application."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from paths import app_base_dir, ensure_runtime_dirs
from templates import DEFAULT_TEMPLATE_ID, get_template, template_categories

ensure_runtime_dirs()
DB_PATH = app_base_dir() / "data" / "worklog.db"
DEFAULT_PERSON_NAME = "默认"
DEFAULT_CATEGORIES = template_categories(DEFAULT_TEMPLATE_ID)

LEGACY_CATEGORY_MAP = {
    "开发": "开发实现类",
    "会议": "日常事务类",
    "测试": "问题治理类",
    "联调": "问题治理类",
    "文档": "方案设计类",
    "学习": "赋能建设类",
    "其他": "日常事务类",
}


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: Path | str | sqlite3.Connection | None = None) -> None:
    """Create or migrate one database without touching any other database."""
    owns_connection = not isinstance(db_path, sqlite3.Connection)
    conn = connect(db_path) if owns_connection else db_path
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                template_id TEXT NOT NULL DEFAULT 'dev',
                active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id INTEGER NOT NULL REFERENCES people(id),
                work_date TEXT NOT NULL CHECK(length(work_date)=10),
                description TEXT NOT NULL,
                hours REAL NOT NULL CHECK(hours > 0 AND hours <= 24),
                category TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES('daily_target_hours', '8.0')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES('activity_template', ?)",
            (DEFAULT_TEMPLATE_ID,),
        )
        conn.execute(
            "INSERT OR IGNORE INTO config(key, value) VALUES('categories', ?)",
            (json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False),),
        )
        conn.execute(
            "INSERT OR IGNORE INTO people(name, template_id) VALUES(?, ?)",
            (DEFAULT_PERSON_NAME, DEFAULT_TEMPLATE_ID),
        )

        columns = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        if "person_id" not in columns:
            conn.execute("ALTER TABLE entries ADD COLUMN person_id INTEGER")
        first_person = conn.execute("SELECT id FROM people ORDER BY id LIMIT 1").fetchone()
        if first_person:
            conn.execute(
                "UPDATE entries SET person_id = ? WHERE person_id IS NULL",
                (first_person[0],),
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entries_person_date "
            "ON entries(person_id, work_date)"
        )
        for old, new in LEGACY_CATEGORY_MAP.items():
            conn.execute(
                "UPDATE entries SET category = ?, updated_at = datetime('now','localtime') "
                "WHERE category = ?",
                (new, old),
            )
        conn.commit()
    finally:
        if owns_connection:
            conn.close()


def _rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def list_people(
    db_path: Path | str | None = None, *, active_only: bool = True
) -> list[dict]:
    with closing(connect(db_path)) as conn:
        where = " WHERE active = 1" if active_only else ""
        return _rows(
            conn,
            "SELECT id, name, template_id, active, created_at FROM people"
            + where
            + " ORDER BY id",
        )


def get_person(person_id: int, db_path: Path | str | None = None) -> dict | None:
    with closing(connect(db_path)) as conn:
        row = conn.execute(
            "SELECT id, name, template_id, active, created_at FROM people WHERE id = ?",
            (int(person_id),),
        ).fetchone()
        return dict(row) if row else None


def add_person(
    name: str,
    template_id: str = DEFAULT_TEMPLATE_ID,
    db_path: Path | str | None = None,
) -> int:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("人员姓名不能为空")
    template_id = get_template(template_id)["id"]
    try:
        with connect(db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO people(name, template_id) VALUES(?, ?)",
                (clean_name, template_id),
            )
            return int(cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"人员「{clean_name}」已存在") from exc


def update_person(
    person_id: int,
    name: str,
    template_id: str,
    db_path: Path | str | None = None,
) -> None:
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("人员姓名不能为空")
    template_id = get_template(template_id)["id"]
    try:
        with connect(db_path) as conn:
            cursor = conn.execute(
                "UPDATE people SET name = ?, template_id = ? WHERE id = ?",
                (clean_name, template_id, int(person_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError("人员不存在")
    except sqlite3.IntegrityError as exc:
        raise ValueError(f"人员「{clean_name}」已存在") from exc


def delete_person(person_id: int, db_path: Path | str | None = None) -> None:
    with connect(db_path) as conn:
        if conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] <= 1:
            raise ValueError("至少保留一名人员")
        count = conn.execute(
            "SELECT COUNT(*) FROM entries WHERE person_id = ?", (int(person_id),)
        ).fetchone()[0]
        if count:
            raise ValueError(f"该人员还有 {count} 条工时记录，不能删除")
        cursor = conn.execute("DELETE FROM people WHERE id = ?", (int(person_id),))
        if cursor.rowcount != 1:
            raise ValueError("人员不存在")


def get_categories(person_id: int, db_path: Path | str | None = None) -> list[str]:
    person = get_person(person_id, db_path)
    return template_categories(person["template_id"] if person else DEFAULT_TEMPLATE_ID)


def add_entry(
    person_id: int,
    work_date: str,
    description: str,
    hours: float,
    category: str,
    notes: str = "",
    db_path: Path | str | None = None,
) -> int:
    description = (description or "").strip()
    category = (category or "").strip()
    hours = float(hours)
    if not description:
        raise ValueError("任务名称不能为空")
    if not 0 < hours <= 24:
        raise ValueError("工时必须大于 0 且不超过 24")
    if category not in get_categories(person_id, db_path):
        raise ValueError("活动类型无效")
    datetime.strptime(work_date, "%Y-%m-%d")
    with connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries(person_id, work_date, description, hours, category, notes)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (int(person_id), work_date, description, hours, category, (notes or "").strip()),
        )
        return int(cursor.lastrowid)


def get_entries(
    start_date: str,
    end_date: str,
    *,
    person_id: int,
    keyword: str = "",
    db_path: Path | str | None = None,
) -> list[dict]:
    sql = """
        SELECT id, person_id, work_date, description, hours, category,
               COALESCE(notes, '') AS notes, created_at, updated_at
        FROM entries
        WHERE person_id = ? AND work_date BETWEEN ? AND ?
    """
    params: list[Any] = [int(person_id), start_date, end_date]
    if keyword.strip():
        sql += " AND (description LIKE ? OR COALESCE(notes, '') LIKE ?)"
        term = f"%{keyword.strip()}%"
        params.extend([term, term])
    sql += " ORDER BY work_date DESC, id DESC"
    with closing(connect(db_path)) as conn:
        return _rows(conn, sql, params)


def update_entry(
    entry_id: int,
    person_id: int,
    *,
    description: str,
    hours: float,
    category: str,
    notes: str = "",
    work_date: str | None = None,
    db_path: Path | str | None = None,
) -> bool:
    description = (description or "").strip()
    hours = float(hours)
    if not description or not 0 < hours <= 24:
        raise ValueError("请填写有效的任务名称和工时")
    if category not in get_categories(person_id, db_path):
        raise ValueError("活动类型无效")
    fields = ["description = ?", "hours = ?", "category = ?", "notes = ?"]
    values: list[Any] = [description, hours, category, (notes or "").strip()]
    if work_date:
        datetime.strptime(work_date, "%Y-%m-%d")
        fields.append("work_date = ?")
        values.append(work_date)
    fields.append("updated_at = datetime('now','localtime')")
    values.extend([int(entry_id), int(person_id)])
    with connect(db_path) as conn:
        cursor = conn.execute(
            f"UPDATE entries SET {', '.join(fields)} WHERE id = ? AND person_id = ?",
            values,
        )
        return cursor.rowcount == 1


def delete_entry(
    entry_id: int, person_id: int, db_path: Path | str | None = None
) -> bool:
    with connect(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM entries WHERE id = ? AND person_id = ?",
            (int(entry_id), int(person_id)),
        )
        return cursor.rowcount == 1


def daily_summary(
    start_date: str,
    end_date: str,
    person_id: int,
    db_path: Path | str | None = None,
) -> list[dict]:
    with closing(connect(db_path)) as conn:
        return _rows(
            conn,
            """
            SELECT work_date, ROUND(SUM(hours), 2) AS total_hours, COUNT(*) AS item_count
            FROM entries
            WHERE person_id = ? AND work_date BETWEEN ? AND ?
            GROUP BY work_date ORDER BY work_date
            """,
            (int(person_id), start_date, end_date),
        )


def category_summary(
    start_date: str,
    end_date: str,
    person_id: int,
    db_path: Path | str | None = None,
) -> list[dict]:
    with closing(connect(db_path)) as conn:
        return _rows(
            conn,
            """
            SELECT category, ROUND(SUM(hours), 2) AS hours, COUNT(*) AS item_count
            FROM entries
            WHERE person_id = ? AND work_date BETWEEN ? AND ?
            GROUP BY category ORDER BY hours DESC
            """,
            (int(person_id), start_date, end_date),
        )


def get_hours_by_date(
    start_date: str,
    end_date: str,
    *,
    person_id: int,
    db_path: Path | str | None = None,
) -> dict[str, float]:
    return {
        row["work_date"]: float(row["total_hours"])
        for row in daily_summary(start_date, end_date, person_id, db_path)
    }


def get_config(
    key: str, default: Any = None, db_path: Path | str | None = None
) -> Any:
    with closing(connect(db_path)) as conn:
        row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    if not row:
        return default
    try:
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return row[0]


def set_config(key: str, value: Any, db_path: Path | str | None = None) -> None:
    encoded = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO config(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, encoded),
        )


def get_daily_target_hours(db_path: Path | str | None = None) -> float:
    try:
        return float(get_config("daily_target_hours", "8.0", db_path))
    except (TypeError, ValueError):
        return 8.0


def backup_database(
    backup_dir: Path | str | None = None,
    keep: int = 10,
    db_path: Path | str | None = None,
) -> Path:
    """Create a transactionally consistent SQLite backup, including WAL data."""
    source_path = Path(db_path) if db_path else DB_PATH
    output_dir = Path(backup_dir) if backup_dir else app_base_dir() / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    destination = output_dir / f"worklog_backup_{stamp}.db"
    with closing(connect(source_path)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"备份完整性检查失败：{result}")
    backups = sorted(
        output_dir.glob("worklog_backup_*.db"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old in backups[max(1, int(keep)) :]:
        old.unlink(missing_ok=True)
    return destination


def export_csv(
    start_date: str,
    end_date: str,
    person_id: int,
    db_path: Path | str | None = None,
) -> bytes:
    person = get_person(person_id, db_path)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["日期", "人员", "任务名称", "时长(h)", "分类", "备注"])
    for row in reversed(get_entries(start_date, end_date, person_id=person_id, db_path=db_path)):
        writer.writerow(
            [row["work_date"], person["name"] if person else "", row["description"], row["hours"], row["category"], row["notes"]]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def import_rows(
    person_id: int,
    rows: list[dict],
    *,
    replace: bool = False,
    db_path: Path | str | None = None,
) -> int:
    """Validate first, then replace/insert within one transaction."""
    categories = set(get_categories(person_id, db_path))
    normalized = []
    for index, row in enumerate(rows, 2):
        try:
            work_date = (row.get("日期") or row.get("work_date") or "").strip()
            datetime.strptime(work_date, "%Y-%m-%d")
            description = (row.get("任务名称") or row.get("工作内容") or row.get("description") or "").strip()
            hours = float(row.get("时长(h)") or row.get("工时") or row.get("hours"))
            category = (row.get("分类") or row.get("活动类型") or row.get("category") or "").strip()
            notes = (row.get("备注") or row.get("notes") or "").strip()
            category = LEGACY_CATEGORY_MAP.get(category, category)
            if not description or not 0 < hours <= 24 or category not in categories:
                raise ValueError
            normalized.append((int(person_id), work_date, description, hours, category, notes))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"CSV 第 {index} 行格式无效") from exc

    if not normalized:
        raise ValueError("CSV 中没有可导入的数据")

    with connect(db_path) as conn:
        if replace:
            conn.execute("DELETE FROM entries WHERE person_id = ?", (int(person_id),))
        conn.executemany(
            "INSERT INTO entries(person_id, work_date, description, hours, category, notes) VALUES(?, ?, ?, ?, ?, ?)",
            normalized,
        )
    return len(normalized)


init_db()
