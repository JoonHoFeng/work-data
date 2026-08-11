#!/usr/bin/env python3
"""
外部 iCal/ICS 订阅：拉取 + 解析。
方向：订阅别人的日历 → 显示在本系统。
"""

from __future__ import annotations

import re
import ssl
import urllib.request
from datetime import date, datetime, timedelta, time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError

FETCH_TIMEOUT = 20


def normalize_ics_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("webcal://"):
        return "https://" + u[len("webcal://") :]
    if u.startswith("webcals://"):
        return "https://" + u[len("webcals://") :]
    return u


def fetch_ics_text(url: str, timeout: int = FETCH_TIMEOUT) -> str:
    url = normalize_ics_url(url)
    if not url.startswith(("http://", "https://")):
        raise ValueError("订阅地址须为 http(s):// 或 webcal:// 开头的 ICS 链接")

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Worklog-ICS-Subscriber/1.0",
            "Accept": "text/calendar, text/plain, */*",
        },
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
    except HTTPError as e:
        raise RuntimeError(f"拉取失败 HTTP {e.code}: {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"网络错误: {e.reason}") from e

    for enc in ("utf-8", "utf-8-sig", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _unfold(ics: str) -> str:
    return re.sub(r"\r\n[ \t]", "", ics.replace("\r\n", "\n").replace("\r", "\n"))


def _unescape(val: str) -> str:
    return (
        val.replace("\\n", "\n")
        .replace("\\N", "\n")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_prop(line: str) -> Tuple[str, Dict[str, str], str]:
    if ":" not in line:
        return line.upper(), {}, ""
    head, value = line.split(":", 1)
    parts = head.split(";")
    name = parts[0].upper()
    params: Dict[str, str] = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k.upper()] = v
        else:
            params[p.upper()] = ""
    return name, params, value


def _parse_dt(value: str, params: Dict[str, str]) -> Tuple[datetime, bool]:
    value = value.strip()
    if params.get("VALUE", "").upper() == "DATE" or (len(value) == 8 and value.isdigit()):
        d = datetime.strptime(value[:8], "%Y%m%d").date()
        return datetime.combine(d, time.min), True

    v = value[:-1] if value.endswith("Z") else value
    if "T" in v:
        if len(v) >= 15:
            return datetime.strptime(v[:15], "%Y%m%dT%H%M%S"), False
        return datetime.strptime(v[:13], "%Y%m%dT%H%M"), False
    d = datetime.strptime(v[:8], "%Y%m%d").date()
    return datetime.combine(d, time.min), True


def _parse_duration(val: str) -> timedelta:
    val = val.strip().upper()
    m = re.fullmatch(
        r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?",
        val,
    )
    if not m:
        return timedelta(hours=1)
    return timedelta(
        weeks=int(m.group(1) or 0),
        days=int(m.group(2) or 0),
        hours=int(m.group(3) or 0),
        minutes=int(m.group(4) or 0),
        seconds=int(m.group(5) or 0),
    )


def _parse_rrule(rrule: str) -> Dict[str, Any]:
    parts: Dict[str, Any] = {}
    for bit in rrule.split(";"):
        if "=" not in bit:
            continue
        k, v = bit.split("=", 1)
        k, v = k.upper(), v.upper()
        if k == "INTERVAL":
            parts[k] = int(v or 1)
        elif k == "COUNT":
            parts[k] = int(v)
        elif k == "UNTIL":
            if "T" in v:
                parts[k] = datetime.strptime(v[:15].rstrip("Z"), "%Y%m%dT%H%M%S").date()
            else:
                parts[k] = datetime.strptime(v[:8], "%Y%m%d").date()
        elif k == "BYDAY":
            map_d = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
            days = set()
            for d in v.split(","):
                d = re.sub(r"[+-]?\d+", "", d)
                if d in map_d:
                    days.add(map_d[d])
            parts[k] = days
        else:
            parts[k] = v
    parts.setdefault("INTERVAL", 1)
    return parts


def _occurrences(
    start: datetime,
    end: datetime,
    rrule: Optional[str],
    range_start: date,
    range_end: date,
) -> List[Tuple[datetime, datetime]]:
    duration = end - start
    if not rrule:
        return [(start, end)]

    rule = _parse_rrule(rrule)
    freq = rule.get("FREQ", "")
    interval = int(rule.get("INTERVAL", 1))
    count = rule.get("COUNT")
    until = rule.get("UNTIL")
    byday = rule.get("BYDAY") or set()

    out: List[Tuple[datetime, datetime]] = []
    hard = 400

    if freq == "DAILY":
        cur = start
        n = 0
        while n < hard:
            if until and cur.date() > until:
                break
            if count is not None and n >= count:
                break
            if cur.date() > range_end:
                break
            if cur.date() >= range_start:
                out.append((cur, cur + duration))
            cur += timedelta(days=interval)
            n += 1
        return out

    if freq == "WEEKLY":
        if byday:
            cur_d = start.date()
            n = 0
            while cur_d <= range_end and n < hard:
                if until and cur_d > until:
                    break
                weeks = (cur_d - start.date()).days // 7
                if (
                    cur_d >= start.date()
                    and cur_d.weekday() in byday
                    and weeks % interval == 0
                ):
                    if cur_d >= range_start:
                        s = datetime.combine(cur_d, start.time())
                        out.append((s, s + duration))
                    n += 1
                    if count is not None and n >= count:
                        break
                cur_d += timedelta(days=1)
            return out

        cur = start
        n = 0
        while n < hard:
            if until and cur.date() > until:
                break
            if count is not None and n >= count:
                break
            if cur.date() > range_end:
                break
            if cur.date() >= range_start:
                out.append((cur, cur + duration))
            cur += timedelta(days=7 * interval)
            n += 1
        return out

    # 其它 RRULE：只保留首场（若在窗口内）
    if range_start <= start.date() <= range_end:
        return [(start, end)]
    return []


def _to_day_rows(
    uid: str,
    summary: str,
    description: str,
    location: str,
    start: datetime,
    end: datetime,
    all_day: bool,
    range_start: date,
    range_end: date,
    recurring: bool,
) -> List[Dict[str, Any]]:
    """把一场事件映射为按天展示的行（跨天拆开）。"""
    rows: List[Dict[str, Any]] = []

    if all_day:
        # DTEND 对全天事件是排他的
        first = start.date()
        last = end.date() - timedelta(days=1) if end.date() > start.date() else start.date()
    else:
        first = start.date()
        last = end.date()
        if end.time() == time.min and end > start:
            last = end.date() - timedelta(days=1)

    day = first
    while day <= last:
        if range_start <= day <= range_end:
            if all_day:
                s_at = f"{day.isoformat()} 00:00:00"
                e_at = f"{day.isoformat()} 23:59:59"
            elif first == last:
                s_at = start.strftime("%Y-%m-%d %H:%M:%S")
                e_at = end.strftime("%Y-%m-%d %H:%M:%S")
            elif day == first:
                s_at = start.strftime("%Y-%m-%d %H:%M:%S")
                e_at = f"{day.isoformat()} 23:59:59"
            elif day == last:
                s_at = f"{day.isoformat()} 00:00:00"
                e_at = end.strftime("%Y-%m-%d %H:%M:%S")
            else:
                s_at = f"{day.isoformat()} 00:00:00"
                e_at = f"{day.isoformat()} 23:59:59"

            inst_uid = f"{uid}_{day.isoformat()}" if recurring or first != last else uid
            rows.append(
                {
                    "uid": inst_uid,
                    "summary": summary,
                    "description": description,
                    "location": location,
                    "start_at": s_at,
                    "end_at": e_at,
                    "all_day": 1 if all_day else 0,
                    "event_date": day.isoformat(),
                }
            )
        day += timedelta(days=1)
    return rows


def parse_ics_events(
    ics_text: str,
    *,
    range_start: Optional[date] = None,
    range_end: Optional[date] = None,
) -> List[Dict[str, Any]]:
    if range_start is None:
        range_start = date.today() - timedelta(days=60)
    if range_end is None:
        range_end = date.today() + timedelta(days=120)

    text = _unfold(ics_text)
    results: List[Dict[str, Any]] = []
    in_event = False
    cur: Dict[str, Any] = {}

    def flush():
        nonlocal cur
        if "dtstart" not in cur:
            cur = {}
            return
        start: datetime = cur["dtstart"]
        all_day = bool(cur.get("all_day"))
        if "dtend" in cur:
            end = cur["dtend"]
        elif "duration" in cur:
            end = start + cur["duration"]
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))

        uid = (cur.get("uid") or f"anon-{start.isoformat()}").strip()
        summary = (cur.get("summary") or "(无标题)").strip()
        description = (cur.get("description") or "").strip()
        location = (cur.get("location") or "").strip()
        rrule = cur.get("rrule")

        for s, e in _occurrences(start, end, rrule, range_start, range_end):
            results.extend(
                _to_day_rows(
                    uid,
                    summary,
                    description,
                    location,
                    s,
                    e,
                    all_day,
                    range_start,
                    range_end,
                    recurring=bool(rrule),
                )
            )
        cur = {}

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        up = line.upper()
        if up == "BEGIN:VEVENT":
            in_event = True
            cur = {}
            continue
        if up == "END:VEVENT":
            if in_event:
                flush()
            in_event = False
            continue
        if not in_event:
            continue

        name, params, value = _parse_prop(line)
        if name == "UID":
            cur["uid"] = value.strip()
        elif name == "SUMMARY":
            cur["summary"] = _unescape(value)
        elif name == "DESCRIPTION":
            cur["description"] = _unescape(value)
        elif name == "LOCATION":
            cur["location"] = _unescape(value)
        elif name == "DTSTART":
            cur["dtstart"], cur["all_day"] = _parse_dt(value, params)
        elif name == "DTEND":
            cur["dtend"], _ = _parse_dt(value, params)
        elif name == "DURATION":
            cur["duration"] = _parse_duration(value)
        elif name == "RRULE":
            cur["rrule"] = value

    # 去重
    seen = set()
    uniq = []
    for r in results:
        k = (r["uid"], r["event_date"], r["start_at"], r["summary"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    uniq.sort(key=lambda x: (x["event_date"], x["start_at"], x["summary"]))
    return uniq


def sync_subscription_from_url(
    url: str,
    *,
    range_start: Optional[date] = None,
    range_end: Optional[date] = None,
) -> List[Dict[str, Any]]:
    text = fetch_ics_text(url)
    return parse_ics_events(text, range_start=range_start, range_end=range_end)
