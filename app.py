#!/usr/bin/env python3
"""Lightweight Flask worklog application."""

from __future__ import annotations

import calendar
import csv
import hmac
import io
import os
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

import db
from templates import ROLE_TEMPLATES, TEMPLATE_DEV, TEMPLATE_QA, get_template

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("WORKLOG_SECRET_KEY") or secrets.token_hex(32),
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("WORKLOG_COOKIE_SECURE", "0") == "1",
)


def _csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(24)
    return session["_csrf"]


@app.before_request
def _security_checks():
    password = os.environ.get("WORKLOG_PASSWORD", "")
    public = {"login", "healthz", "static"}
    if password and request.endpoint not in public and not session.get("authenticated"):
        return redirect(url_for("login"))
    if request.method == "POST":
        supplied = request.form.get("_csrf", "")
        if not supplied or not hmac.compare_digest(supplied, _csrf_token()):
            abort(400, "CSRF validation failed")
    return None


@app.context_processor
def _template_context():
    return {
        "csrf_token": _csrf_token,
        "templates": ROLE_TEMPLATES,
        "today": date.today().isoformat(),
        "auth_enabled": bool(os.environ.get("WORKLOG_PASSWORD")),
    }


def _parse_date(value: str | None, default: date) -> date:
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        return default


def _return_path(default_endpoint: str = "dashboard") -> str:
    value = request.form.get("return_to", "")
    if value.startswith("/") and not value.startswith("//"):
        return value
    return url_for(default_endpoint)


def _current_person() -> dict:
    people = db.list_people()
    if not people:
        db.add_person("默认")
        people = db.list_people()
    person_id = session.get("person_id")
    person = next((item for item in people if item["id"] == person_id), None)
    if not person:
        person = people[0]
        session["person_id"] = person["id"]
    return person


def _month_shift(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


@app.get("/login")
@app.post("/login")
def login():
    if not os.environ.get("WORKLOG_PASSWORD"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        expected = os.environ.get("WORKLOG_PASSWORD", "")
        supplied = request.form.get("password", "")
        if hmac.compare_digest(supplied, expected):
            session.clear()
            session["authenticated"] = True
            flash("登录成功", "success")
            return redirect(url_for("dashboard"))
        flash("密码不正确", "error")
    return render_template("login.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/people/select")
def select_person():
    person = db.get_person(int(request.form.get("person_id", 0)))
    if person:
        session["person_id"] = person["id"]
    return redirect(_return_path())


@app.get("/")
def dashboard():
    person = _current_person()
    selected = _parse_date(request.args.get("date"), date.today())
    target = db.get_daily_target_hours()

    month_start = selected.replace(day=1)
    month_end = _month_shift(month_start, 1) - timedelta(days=1)
    week_start = selected - timedelta(days=selected.weekday())
    week_end = week_start + timedelta(days=6)

    day_entries = db.get_entries(
        selected.isoformat(), selected.isoformat(), person_id=person["id"]
    )
    week_daily = db.daily_summary(
        week_start.isoformat(), week_end.isoformat(), person["id"]
    )
    month_daily = db.daily_summary(
        month_start.isoformat(), month_end.isoformat(), person["id"]
    )
    month_categories = db.category_summary(
        month_start.isoformat(), month_end.isoformat(), person["id"]
    )
    hours_by_day = {row["work_date"]: float(row["total_hours"]) for row in month_daily}

    calendar_rows = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(
        selected.year, selected.month
    ):
        row = []
        for item in week:
            if item.month != selected.month:
                row.append(None)
                continue
            hours = hours_by_day.get(item.isoformat(), 0.0)
            level = "ok" if hours >= target else "partial" if hours > 0 else "empty"
            row.append(
                {
                    "date": item.isoformat(),
                    "day": item.day,
                    "hours": hours,
                    "level": level,
                    "selected": item == selected,
                }
            )
        calendar_rows.append(row)

    week_total = sum(float(row["total_hours"]) for row in week_daily)
    month_total = sum(float(row["total_hours"]) for row in month_daily)
    day_total = sum(float(row["hours"]) for row in day_entries)
    max_category = max((float(row["hours"]) for row in month_categories), default=1.0)
    for row in month_categories:
        row["percent"] = round(float(row["hours"]) / max_category * 100, 1)

    return render_template(
        "dashboard.html",
        people=db.list_people(),
        person=person,
        categories=db.get_categories(person["id"]),
        selected=selected,
        target=target,
        day_entries=day_entries,
        day_total=day_total,
        week_total=week_total,
        month_total=month_total,
        week_start=week_start,
        week_end=week_end,
        month_start=month_start,
        month_end=month_end,
        month_categories=month_categories,
        calendar_rows=calendar_rows,
        prev_month=_month_shift(month_start, -1).isoformat(),
        next_month=_month_shift(month_start, 1).isoformat(),
    )


@app.post("/entries")
def create_entry():
    person = _current_person()
    work_date = request.form.get("work_date", date.today().isoformat())
    try:
        db.add_entry(
            person["id"],
            work_date,
            request.form.get("description", ""),
            float(request.form.get("hours", 0)),
            request.form.get("category", ""),
            request.form.get("notes", ""),
        )
        flash("工作记录已保存", "success")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("dashboard", date=work_date))


@app.post("/entries/<int:entry_id>/update")
def edit_entry(entry_id: int):
    person = _current_person()
    return_to = _return_path()
    try:
        changed = db.update_entry(
            entry_id,
            person["id"],
            description=request.form.get("description", ""),
            hours=float(request.form.get("hours", 0)),
            category=request.form.get("category", ""),
            notes=request.form.get("notes", ""),
            work_date=request.form.get("work_date"),
        )
        flash("记录已更新" if changed else "记录不存在或不属于当前人员", "success" if changed else "error")
    except (TypeError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(return_to)


@app.post("/entries/<int:entry_id>/delete")
def remove_entry(entry_id: int):
    person = _current_person()
    deleted = db.delete_entry(entry_id, person["id"])
    flash("记录已删除" if deleted else "记录不存在或不属于当前人员", "success" if deleted else "error")
    return redirect(_return_path())


@app.get("/history")
def history():
    person = _current_person()
    end = _parse_date(request.args.get("end"), date.today())
    start = _parse_date(request.args.get("start"), end - timedelta(days=30))
    keyword = request.args.get("q", "").strip()
    entries = db.get_entries(
        start.isoformat(),
        end.isoformat(),
        person_id=person["id"],
        keyword=keyword,
    )
    return render_template(
        "history.html",
        people=db.list_people(),
        person=person,
        categories=db.get_categories(person["id"]),
        entries=entries,
        start=start,
        end=end,
        keyword=keyword,
    )


@app.get("/settings")
def settings():
    person = _current_person()
    return render_template(
        "settings.html",
        people=db.list_people(active_only=False),
        person=person,
        target=db.get_daily_target_hours(),
    )


@app.post("/settings/people")
def create_person():
    try:
        db.add_person(request.form.get("name", ""), request.form.get("template_id", TEMPLATE_DEV))
        flash("人员已添加", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings"))


@app.post("/settings/people/<int:person_id>")
def edit_person(person_id: int):
    try:
        db.update_person(
            person_id,
            request.form.get("name", ""),
            request.form.get("template_id", TEMPLATE_DEV),
        )
        flash("人员设置已保存", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings"))


@app.post("/settings/people/<int:person_id>/delete")
def remove_person(person_id: int):
    try:
        db.delete_person(person_id)
        if session.get("person_id") == person_id:
            session.pop("person_id", None)
        flash("人员已删除", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings"))


@app.post("/settings/target")
def update_target():
    try:
        target = float(request.form.get("target", 0))
        if not 0 < target <= 24:
            raise ValueError("目标工时必须大于 0 且不超过 24")
        db.set_config("daily_target_hours", target)
        flash("目标工时已保存", "success")
    except ValueError as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings"))


@app.post("/settings/backup")
def create_backup():
    path = db.backup_database(keep=10)
    flash(f"备份完成：{path.name}", "success")
    return redirect(url_for("settings"))


@app.get("/export.csv")
def download_csv():
    person = _current_person()
    start = request.args.get("start") or date.today().replace(month=1, day=1).isoformat()
    end = request.args.get("end") or date.today().isoformat()
    content = db.export_csv(start, end, person["id"])
    return send_file(
        io.BytesIO(content),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"worklog_{person['name']}_{start}_{end}.csv",
    )


@app.post("/import.csv")
def upload_csv():
    person = _current_person()
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        flash("请选择 CSV 文件", "error")
        return redirect(url_for("settings"))
    try:
        text = uploaded.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        replace = request.form.get("mode") == "replace"
        if replace:
            db.backup_database(keep=10)
        count = db.import_rows(person["id"], rows, replace=replace)
        flash(f"成功导入 {count} 条记录", "success")
    except (UnicodeDecodeError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("settings"))


if __name__ == "__main__":
    app.run(
        host=os.environ.get("WORKLOG_ADDRESS", "127.0.0.1"),
        port=int(os.environ.get("WORKLOG_PORT", "8501")),
        debug=False,
    )
