#!/usr/bin/env python3
"""
工作日志 DB 层
- 使用标准库 sqlite3 + pandas
- 所有日期统一用 'YYYY-MM-DD' 字符串存储
- 支持高亮（is_highlight）用于周/月复盘重点展示
"""

import sqlite3
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import json

DB_PATH = Path("data/worklog.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# 默认分类（可被 config 覆盖）
DEFAULT_CATEGORIES = ["开发", "会议", "测试", "联调", "文档", "学习", "其他"]


def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """获取数据库连接（自动启用外键和中文支持）"""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path), detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # 更好并发（单用户也无害）
    return conn


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """初始化表结构（幂等）"""
    if conn is None:
        conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            work_date TEXT NOT NULL CHECK(length(work_date)=10),
            description TEXT NOT NULL,
            hours REAL NOT NULL CHECK(hours > 0),
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'done' CHECK(status IN ('done','in_progress','planned')),
            notes TEXT,
            is_highlight INTEGER NOT NULL DEFAULT 0 CHECK(is_highlight IN (0,1)),
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_date ON entries(work_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_status_date ON entries(status, work_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_category ON entries(category)")

    # 配置表（分类列表、目标工时等）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    # 写入默认配置（如果不存在）
    cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                ("categories", json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False)))
    cur.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
                ("daily_target_hours", "8.0"))

    conn.commit()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_work_items(items: List[Dict[str, Any]], db_path: Optional[Path] = None) -> List[int]:
    """
    批量插入工作项
    items: [{work_date, description, hours, category, status, notes?, is_highlight?}, ...]
    返回新插入的 id 列表
    """
    if not items:
        return []

    conn = get_conn(db_path)
    cur = conn.cursor()
    ids = []

    for it in items:
        cur.execute("""
            INSERT INTO entries
            (work_date, description, hours, category, status, notes, is_highlight, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            it["work_date"],
            it["description"].strip(),
            float(it["hours"]),
            it["category"],
            it.get("status", "done"),
            it.get("notes", "").strip() or None,
            1 if it.get("is_highlight") else 0,
            _now()
        ))
        ids.append(cur.lastrowid)

    conn.commit()
    conn.close()
    return ids


def get_entries(
    start_date: str,
    end_date: str,
    status: Optional[str] = None,
    db_path: Optional[Path] = None
) -> pd.DataFrame:
    """
    按日期范围查询，返回 pandas DataFrame（按日期、id 排序）
    """
    conn = get_conn(db_path)
    sql = """
        SELECT id, work_date, description, hours, category, status, notes, is_highlight,
               created_at, updated_at
        FROM entries
        WHERE work_date BETWEEN ? AND ?
    """
    params = [start_date, end_date]
    if status:
        sql += " AND status = ?"
        params.append(status)

    sql += " ORDER BY work_date, id"
    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()

    if not df.empty:
        df["is_highlight"] = df["is_highlight"].astype(bool)
    return df


def update_entry(entry_id: int, **fields: Any) -> bool:
    """更新单条记录（支持部分字段）"""
    if not fields:
        return False

    allowed = {"description", "hours", "category", "status", "notes", "is_highlight", "work_date"}
    update_fields = {k: v for k, v in fields.items() if k in allowed}
    if not update_fields:
        return False

    if "is_highlight" in update_fields:
        update_fields["is_highlight"] = 1 if update_fields["is_highlight"] else 0

    update_fields["updated_at"] = _now()

    conn = get_conn()
    cur = conn.cursor()
    set_clause = ", ".join(f"{k} = ?" for k in update_fields)
    cur.execute(f"UPDATE entries SET {set_clause} WHERE id = ?", list(update_fields.values()) + [entry_id])
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def delete_entry(entry_id: int) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# ==================== 聚合查询（供 UI 和报告使用） ====================

def get_daily_summary(start_date: str, end_date: str, db_path: Optional[Path] = None) -> pd.DataFrame:
    """每日汇总：总工时、条目数、完成数、高亮数"""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT
            work_date,
            SUM(hours) as total_hours,
            COUNT(*) as item_count,
            SUM(CASE WHEN status='done' THEN 1 ELSE 0 END) as done_count,
            SUM(CASE WHEN is_highlight=1 THEN 1 ELSE 0 END) as highlight_count
        FROM entries
        WHERE work_date BETWEEN ? AND ?
        GROUP BY work_date
        ORDER BY work_date
    """, conn, params=[start_date, end_date])
    conn.close()
    return df


def get_weekly_completed(week_start: str, db_path: Optional[Path] = None) -> pd.DataFrame:
    """本周所有已完成（含高亮）事项，按日期和时长排序"""
    week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    df = get_entries(week_start, week_end, db_path=db_path)
    if df.empty:
        return df
    done = df[df["status"] == "done"].copy()
    done = done.sort_values(["is_highlight", "hours"], ascending=[False, False])
    return done


def get_category_breakdown(start_date: str, end_date: str, db_path: Optional[Path] = None) -> pd.DataFrame:
    """分类统计（仅统计 done + in_progress）"""
    conn = get_conn(db_path)
    df = pd.read_sql_query("""
        SELECT category, SUM(hours) as hours, COUNT(*) as count
        FROM entries
        WHERE work_date BETWEEN ? AND ?
          AND status IN ('done', 'in_progress')
        GROUP BY category
        ORDER BY hours DESC
    """, conn, params=[start_date, end_date])
    conn.close()
    return df


def get_highlights(start_date: str, end_date: str, db_path: Optional[Path] = None) -> pd.DataFrame:
    """高亮事项（周/月复盘用）"""
    df = get_entries(start_date, end_date, db_path=db_path)
    if df.empty:
        return df
    return df[df["is_highlight"] == True].sort_values(["work_date", "hours"], ascending=[True, False])


def get_config(key: str, default: Any = None, db_path: Optional[Path] = None) -> Any:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("SELECT value FROM config WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    val = row[0]
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def set_config(key: str, value: Any, db_path: Optional[Path] = None) -> None:
    conn = get_conn(db_path)
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_all_categories(db_path: Optional[Path] = None) -> List[str]:
    cats = get_config("categories", DEFAULT_CATEGORIES, db_path)
    return cats if isinstance(cats, list) else DEFAULT_CATEGORIES


def set_categories(categories: List[str], db_path: Optional[Path] = None) -> None:
    set_config("categories", categories, db_path)


def get_daily_target_hours(db_path: Optional[Path] = None) -> float:
    val = get_config("daily_target_hours", "8.0", db_path)
    try:
        return float(val)
    except (ValueError, TypeError):
        return 8.0


if __name__ == "__main__":
    # 简单自测
    init_db()
    print("DB initialized at", DB_PATH)
    print("Categories:", get_all_categories())
    print("Target hours:", get_daily_target_hours())
