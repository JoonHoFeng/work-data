#!/usr/bin/env python3
"""UI 共用常量与小工具。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, List
import re

from db import (
    list_ical_subscriptions,
    replace_ical_events,
    mark_ical_sync_error,
    get_config,
    set_config,
)
from ical_client import sync_subscription_from_url

STATUS_DISPLAY = {
    "done": "✅ 已完成",
    "in_progress": "🔄 进行中",
    "planned": "📌 计划中",
}
STATUS_OPTIONS = list(STATUS_DISPLAY.values())
STATUS_REVERSE = {v: k for k, v in STATUS_DISPLAY.items()}

# 旧分类 → 研发模板映射（历史数据清洗）
LEGACY_CATEGORY_MAP = {
    "开发": "开发实现类",
    "会议": "日常事务类",
    "测试": "问题治理类",
    "联调": "问题治理类",
    "文档": "方案设计类",
    "学习": "赋能建设类",
    "其他": "日常事务类",
}


def get_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def format_hours(h: float) -> str:
    return f"{h:.1f}h"


def status_badge(status: str) -> str:
    return STATUS_DISPLAY.get(status, status)


def format_event_time(start_at: str, end_at: str, all_day: bool) -> str:
    if all_day:
        return "全天"
    try:
        s = datetime.strptime(str(start_at)[:19], "%Y-%m-%d %H:%M:%S")
        e = datetime.strptime(str(end_at)[:19], "%Y-%m-%d %H:%M:%S")
        return f"{s.strftime('%H:%M')}–{e.strftime('%H:%M')}"
    except Exception:
        return str(start_at)[11:16] if len(str(start_at)) >= 16 else ""


def short_cal_event_name(summary: str) -> str:
    s = (summary or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s*第\d+\s*天\s*/\s*共\s*\d+\s*天\s*", "", s)
    is_work = "补班" in s
    s = s.replace("补班", "").replace("假期", "").replace("节日", "").strip()
    s = re.sub(r"\s+", "", s)
    base = s[:4] if s else ("补班" if is_work else "日程")
    if is_work:
        return "补班" if base in ("", "补班") else f"{base}班"
    return base[:5]


def sync_all_ical_subscriptions(days_back: int = 60, days_forward: int = 120) -> Dict[str, Any]:
    start = date.today() - timedelta(days=days_back)
    end = date.today() + timedelta(days=days_forward)
    subs = list_ical_subscriptions()
    ok_n, fail_n, total_events = 0, 0, 0
    errors: List[str] = []
    for sub in subs:
        if not sub.get("enabled"):
            continue
        try:
            events = sync_subscription_from_url(
                sub["url"], range_start=start, range_end=end
            )
            n = replace_ical_events(sub["id"], events, error=None)
            ok_n += 1
            total_events += n
        except Exception as e:  # noqa: BLE001
            fail_n += 1
            msg = str(e)
            mark_ical_sync_error(sub["id"], msg)
            errors.append(f"{sub.get('name') or sub.get('url')}: {msg}")
    return {"ok": ok_n, "fail": fail_n, "events": total_events, "errors": errors}


def maybe_auto_sync_ical() -> Dict[str, Any] | None:
    """每天最多自动同步一次外部日历。返回同步结果或 None（跳过）。"""
    today = date.today().isoformat()
    last = get_config("ical_last_auto_sync", "")
    if str(last) == today:
        return None
    enabled = [s for s in list_ical_subscriptions() if s.get("enabled")]
    if not enabled:
        set_config("ical_last_auto_sync", today)
        return None
    result = sync_all_ical_subscriptions()
    set_config("ical_last_auto_sync", today)
    return result
