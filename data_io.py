#!/usr/bin/env python3
"""
工时数据导入 / 导出（CSV / Excel）。
列约定（中英均可）：
  work_date / 日期
  description / 任务名称 / 工作内容
  hours / 时长 / 工时
  category / 分类 / 活动类型
  notes / 备注 / 工作内容详情（可选）
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from db import add_work_items, get_conn, get_entries, LEGACY_CATEGORY_MAP

# 导出列（对用户友好的中文表头）
EXPORT_COLUMNS = ["日期", "任务名称", "时长(h)", "分类", "备注"]

_COL_MAP = {
    "日期": "work_date",
    "date": "work_date",
    "work_date": "work_date",
    "工作日期": "work_date",
    "任务名称": "description",
    "工作内容": "description",
    "描述": "description",
    "description": "description",
    "title": "description",
    "时长": "hours",
    "时长(h)": "hours",
    "工时": "hours",
    "hours": "hours",
    "hour": "hours",
    "分类": "category",
    "活动类型": "category",
    "category": "category",
    "type": "category",
    "备注": "notes",
    "说明": "notes",
    "notes": "notes",
    "detail": "notes",
    "工作内容详情": "notes",
}


def _normalize_date(val: Any) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val.date().isoformat()
    if isinstance(val, date):
        return val.isoformat()
    s = str(val).strip()
    if not s:
        return None
    # Excel serial date
    if re.fullmatch(r"\d+(\.\d+)?", s):
        try:
            num = float(s)
            if 20000 < num < 60000:  # rough Excel serial range
                dt = pd.to_datetime(num, unit="D", origin="1899-12-30")
                return dt.date().isoformat()
        except Exception:
            pass
    try:
        dt = pd.to_datetime(s, errors="raise")
        return dt.date().isoformat()
    except Exception:
        # YYYY/MM/DD or YYYY.MM.DD
        s2 = s.replace("/", "-").replace(".", "-")
        try:
            dt = pd.to_datetime(s2, errors="raise")
            return dt.date().isoformat()
        except Exception:
            return None


def _normalize_hours(val: Any) -> Optional[float]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        h = float(val)
        if h <= 0:
            return None
        return round(h, 2)
    except (TypeError, ValueError):
        s = str(val).strip().lower().replace("h", "").replace("小时", "").strip()
        try:
            h = float(s)
            return round(h, 2) if h > 0 else None
        except ValueError:
            return None


def export_entries_df(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path=None,
) -> pd.DataFrame:
    """导出为中文列表头 DataFrame。"""
    if not start_date:
        start_date = "2000-01-01"
    if not end_date:
        end_date = "2100-12-31"
    df = get_entries(start_date, end_date, db_path=db_path)
    if df.empty:
        return pd.DataFrame(columns=EXPORT_COLUMNS)
    out = pd.DataFrame({
        "日期": df["work_date"],
        "任务名称": df["description"],
        "时长(h)": df["hours"],
        "分类": df["category"],
        "备注": df["notes"].fillna(""),
    })
    return out


def export_to_csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    # Excel 友好 BOM
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def export_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="工时明细")
    return buf.getvalue()


def read_upload_to_df(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """根据扩展名读取上传文件。"""
    name = (file_name or "").lower()
    bio = io.BytesIO(file_bytes)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(bio)
    # csv / txt
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            bio.seek(0)
            return pd.read_csv(bio, encoding=enc)
        except Exception:
            continue
    bio.seek(0)
    return pd.read_csv(bio)


def normalize_import_df(df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    标准化导入表，返回 (items, errors)。
    items 可直接 add_work_items。
    """
    if df is None or df.empty:
        return [], ["文件为空"]

    # 列名去空白
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    rename = {}
    for c in df.columns:
        key = c.strip()
        low = key.lower()
        if key in _COL_MAP:
            rename[c] = _COL_MAP[key]
        elif low in _COL_MAP:
            rename[c] = _COL_MAP[low]
    df = df.rename(columns=rename)

    required = ["work_date", "description", "hours", "category"]
    missing = [r for r in required if r not in df.columns]
    if missing:
        return [], [
            f"缺少必要列：{', '.join(missing)}。"
            f"请使用表头：日期, 任务名称, 时长(h), 分类, 备注"
        ]

    items: List[Dict[str, Any]] = []
    errors: List[str] = []
    for i, row in df.iterrows():
        row_no = int(i) + 2  # 表头占 1 行
        wd = _normalize_date(row.get("work_date"))
        desc = str(row.get("description") or "").strip()
        hours = _normalize_hours(row.get("hours"))
        cat = str(row.get("category") or "").strip()
        notes = row.get("notes", "")
        if notes is None or (isinstance(notes, float) and pd.isna(notes)):
            notes = ""
        else:
            notes = str(notes).strip()

        if not wd and not desc and hours is None and not cat:
            continue  # 空行

        if not wd:
            errors.append(f"第 {row_no} 行：日期无效")
            continue
        if not desc:
            errors.append(f"第 {row_no} 行：任务名称为空")
            continue
        if hours is None:
            errors.append(f"第 {row_no} 行：时长无效")
            continue
        if not cat:
            errors.append(f"第 {row_no} 行：分类为空")
            continue

        # 旧分类自动映射
        cat = LEGACY_CATEGORY_MAP.get(cat, cat)

        items.append({
            "work_date": wd,
            "description": desc,
            "hours": hours,
            "category": cat,
            "notes": notes,
            "status": "done",
        })

    return items, errors


def import_entries(
    items: List[Dict[str, Any]],
    *,
    mode: str = "append",
    db_path=None,
) -> Dict[str, Any]:
    """
    mode:
      - append: 追加
      - replace: 清空全部工时后导入
    """
    if mode == "replace":
        conn = get_conn(db_path)
        conn.execute("DELETE FROM entries")
        conn.commit()
        conn.close()

    ids = add_work_items(items, db_path=db_path)
    return {"inserted": len(ids), "ids": ids, "mode": mode}


def download_template_csv_bytes() -> bytes:
    sample = pd.DataFrame([
        {
            "日期": date.today().isoformat(),
            "任务名称": "示例：完成接口联调",
            "时长(h)": 2.0,
            "分类": "开发实现类",
            "备注": "可删",
        }
    ])
    return export_to_csv_bytes(sample)
