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

from templates import (  # noqa: E402
    TEMPLATE_DEV,
    get_template,
    template_categories,
)

# 默认：研发人员模板
DEFAULT_TEMPLATE_ID = TEMPLATE_DEV
DEFAULT_CATEGORIES = template_categories(DEFAULT_TEMPLATE_ID)

# 旧版默认分类（用于一次性迁移到研发 7 类）
_LEGACY_DEFAULT_CATEGORIES = ["开发", "会议", "测试", "联调", "文档", "学习", "其他"]


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
    cur.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("categories", json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False)),
    )
    cur.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("daily_target_hours", "8.0"),
    )
    cur.execute(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        ("activity_template", DEFAULT_TEMPLATE_ID),
    )

    # 若仍是旧版 7 类（开发/会议/…），自动迁移为研发模板
    cur.execute("SELECT value FROM config WHERE key = ?", ("categories",))
    row = cur.fetchone()
    if row:
        try:
            cats = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            cats = None
        if isinstance(cats, list) and cats == _LEGACY_DEFAULT_CATEGORIES:
            cur.execute(
                "UPDATE config SET value = ? WHERE key = ?",
                (json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False), "categories"),
            )
            cur.execute(
                "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                ("activity_template", DEFAULT_TEMPLATE_ID),
            )

    # 外部日历订阅（iCal/ICS → 本系统展示）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ical_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            color TEXT NOT NULL DEFAULT '#2563eb',
            last_sync TEXT,
            last_error TEXT,
            event_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ical_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            uid TEXT NOT NULL,
            summary TEXT NOT NULL,
            description TEXT,
            location TEXT,
            start_at TEXT NOT NULL,
            end_at TEXT NOT NULL,
            all_day INTEGER NOT NULL DEFAULT 0 CHECK(all_day IN (0,1)),
            event_date TEXT NOT NULL,
            FOREIGN KEY(subscription_id) REFERENCES ical_subscriptions(id) ON DELETE CASCADE,
            UNIQUE(subscription_id, uid, event_date, start_at)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_ical_events_date ON ical_events(event_date)")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ical_events_sub_date ON ical_events(subscription_id, event_date)"
    )

    conn.commit()

    # 历史 entries 旧分类名映射（幂等，migrate 自建连接）
    migrate_legacy_entry_categories()


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


def get_activity_template(db_path: Optional[Path] = None) -> str:
    """当前活动类型模板 ID：dev | qa"""
    val = get_config("activity_template", DEFAULT_TEMPLATE_ID, db_path)
    if val in ("dev", "qa"):
        return str(val)
    return DEFAULT_TEMPLATE_ID


def apply_activity_template(template_id: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    切换固定模板：写入 template id，并重置分类列表为该模板标准 7 类。
    返回模板信息。
    """
    t = get_template(template_id)
    tid = t["id"]
    cats = list(t["categories"])
    set_config("activity_template", tid, db_path)
    set_categories(cats, db_path)
    return t


# 旧版工时分类 → 研发模板（历史数据一次性映射）
LEGACY_CATEGORY_MAP = {
    "开发": "开发实现类",
    "会议": "日常事务类",
    "测试": "问题治理类",
    "联调": "问题治理类",
    "文档": "方案设计类",
    "学习": "赋能建设类",
    "其他": "日常事务类",
}


def migrate_legacy_entry_categories(db_path: Optional[Path] = None) -> int:
    """
    将 entries 中旧分类名映射为研发 7 类。返回更新条数。
    幂等：已是新名的不再改。
    """
    conn = get_conn(db_path)
    cur = conn.cursor()
    updated = 0
    for old, new in LEGACY_CATEGORY_MAP.items():
        cur.execute(
            "UPDATE entries SET category = ?, updated_at = ? WHERE category = ?",
            (new, _now(), old),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()
    return updated


def backup_database(backup_dir: Optional[Path] = None, keep: int = 10) -> Path:
    """备份 data/worklog.db 到 reports/，保留最近 keep 份。"""
    import shutil

    src = DB_PATH
    out_dir = Path(backup_dir) if backup_dir else Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = out_dir / f"worklog_backup_{ts}.db"
    shutil.copy2(src, dst)

    backups = sorted(
        out_dir.glob("worklog_backup_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
    return dst


# ==================== 外部日历订阅 ====================

def list_ical_subscriptions(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, name, url, enabled, color, last_sync, last_error, event_count, created_at
        FROM ical_subscriptions
        ORDER BY id
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def add_ical_subscription(
    name: str,
    url: str,
    color: str = "#2563eb",
    db_path: Optional[Path] = None,
) -> int:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO ical_subscriptions (name, url, color)
        VALUES (?, ?, ?)
        """,
        (name.strip(), url.strip(), color or "#2563eb"),
    )
    sid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return sid


def delete_ical_subscription(sub_id: int, db_path: Optional[Path] = None) -> bool:
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ical_events WHERE subscription_id = ?", (sub_id,))
    cur.execute("DELETE FROM ical_subscriptions WHERE id = ?", (sub_id,))
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def set_ical_subscription_enabled(
    sub_id: int, enabled: bool, db_path: Optional[Path] = None
) -> None:
    conn = get_conn(db_path)
    conn.execute(
        "UPDATE ical_subscriptions SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, sub_id),
    )
    conn.commit()
    conn.close()


def replace_ical_events(
    sub_id: int,
    events: List[Dict[str, Any]],
    *,
    error: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """用新拉取的事件整体替换某订阅的缓存。"""
    conn = get_conn(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM ical_events WHERE subscription_id = ?", (sub_id,))
    n = 0
    for ev in events:
        cur.execute(
            """
            INSERT OR IGNORE INTO ical_events
            (subscription_id, uid, summary, description, location, start_at, end_at, all_day, event_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sub_id,
                ev.get("uid") or "",
                ev.get("summary") or "(无标题)",
                ev.get("description") or "",
                ev.get("location") or "",
                ev.get("start_at"),
                ev.get("end_at"),
                1 if ev.get("all_day") else 0,
                ev.get("event_date"),
            ),
        )
        n += 1
    cur.execute(
        """
        UPDATE ical_subscriptions
        SET last_sync = ?, last_error = ?, event_count = ?
        WHERE id = ?
        """,
        (_now(), error, n if error is None else 0, sub_id),
    )
    conn.commit()
    conn.close()
    return n


def mark_ical_sync_error(sub_id: int, error: str, db_path: Optional[Path] = None) -> None:
    conn = get_conn(db_path)
    conn.execute(
        """
        UPDATE ical_subscriptions
        SET last_sync = ?, last_error = ?
        WHERE id = ?
        """,
        (_now(), error, sub_id),
    )
    conn.commit()
    conn.close()


def get_ical_events(
    start_date: str,
    end_date: str,
    db_path: Optional[Path] = None,
) -> pd.DataFrame:
    """查询已启用订阅在日期范围内的缓存事件。"""
    conn = get_conn(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            e.id,
            e.subscription_id,
            s.name AS source_name,
            s.color AS source_color,
            e.uid,
            e.summary,
            e.description,
            e.location,
            e.start_at,
            e.end_at,
            e.all_day,
            e.event_date
        FROM ical_events e
        JOIN ical_subscriptions s ON s.id = e.subscription_id
        WHERE s.enabled = 1
          AND e.event_date BETWEEN ? AND ?
        ORDER BY e.event_date, e.start_at, e.id
        """,
        conn,
        params=[start_date, end_date],
    )
    conn.close()
    if not df.empty:
        df["all_day"] = df["all_day"].astype(bool)
    return df


if __name__ == "__main__":
    # 简单自测
    init_db()
    print("DB initialized at", DB_PATH)
    print("Categories:", get_all_categories())
    print("Target hours:", get_daily_target_hours())
