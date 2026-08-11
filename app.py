#!/usr/bin/env python3
"""
工作日志管理系统 - Streamlit 主应用
运行：streamlit run app.py
"""

import html as html_lib
import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import calendar
from pathlib import Path
from typing import Dict
import sys

# 确保能导入本地模块（开发 / PyInstaller 打包）
from paths import app_base_dir, bundle_dir, ensure_runtime_dirs

ROOT = ensure_runtime_dirs()
_BUNDLE = bundle_dir()
# 打包后 scripts 在 _MEIPASS/scripts；开发时在项目根/scripts
for _p in (_BUNDLE, _BUNDLE / "scripts", ROOT, ROOT / "scripts"):
    _ps = str(_p)
    if _p.exists() and _ps not in sys.path:
        sys.path.insert(0, _ps)
# 工作目录固定到可写根目录，便于 data/reports 相对路径
import os as _os
_os.chdir(ROOT)


def _load_generate_monthly_report():
    """兼容开发 import 与 PyInstaller 打包路径。"""
    import importlib
    import importlib.util

    errors = []
    for mod_name in ("scripts.generate_report", "generate_report"):
        try:
            return importlib.import_module(mod_name).generate_monthly_report
        except Exception as e:  # noqa: BLE001
            errors.append(f"{mod_name}: {e}")

    # 直接按文件路径加载
    candidates = [
        _BUNDLE / "scripts" / "generate_report.py",
        _BUNDLE / "generate_report.py",
        ROOT / "scripts" / "generate_report.py",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("generate_report", path)
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)
            return mod.generate_monthly_report
        except Exception as e:  # noqa: BLE001
            errors.append(f"{path}: {e}")

    raise ImportError("无法加载 generate_monthly_report: " + " | ".join(errors))


from db import (
    init_db, add_work_items, get_entries, update_entry, delete_entry,
    get_daily_summary, get_category_breakdown,
    get_all_categories, set_categories,
    get_daily_target_hours, set_config, backup_database,
    get_activity_template, apply_activity_template,
    list_ical_subscriptions, add_ical_subscription, delete_ical_subscription,
    set_ical_subscription_enabled, replace_ical_events, mark_ical_sync_error,
    get_ical_events,
)
from ical_client import sync_subscription_from_url, normalize_ics_url
from templates import (
    ROLE_TEMPLATES,
    TEMPLATE_DEV,
    TEMPLATE_QA,
    get_template,
    format_help_markdown,
    template_categories,
)
from ui_helpers import (
    get_week_start, format_hours,
    format_event_time, short_cal_event_name,
    sync_all_ical_subscriptions, maybe_auto_sync_ical,
)
generate_monthly_report = _load_generate_monthly_report()

st.set_page_config(
    page_title="工作日志",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        "Get help": None,
        "Report a bug": None,
        "About": "### 工作日志\n\n个人工时与完成事项追踪工具。\n\n本地 SQLite 存储，数据仅保存在本机。",
    },
)

# 布局样式（不覆盖主题背景，兼容 light/dark）
st.markdown(
    """
    <style>
    /* 去掉右上角 Deploy 按钮 */
    .stDeployButton,
    [data-testid="stAppDeployButton"],
    div[data-testid="stDecoration"] {
        display: none !important;
        visibility: hidden !important;
    }
    header[data-testid="stHeader"] a[href*="share.streamlit.io"] {
        display: none !important;
    }

    /* 隐藏原生可拖拽侧边栏与折叠按钮，改用固定 1:2 分栏 */
    section[data-testid="stSidebar"],
    div[data-testid="stSidebarCollapsedControl"],
    div[data-testid="collapsedControl"] {
        display: none !important;
    }
    /* 主内容区占满 */
    div[data-testid="stAppViewContainer"] > div {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    /* 日历网格：日期按钮强制单行 */
    div[data-testid="stHorizontalBlock"] button {
        white-space: nowrap !important;
        min-width: 0 !important;
        padding-left: 0.1rem !important;
        padding-right: 0.1rem !important;
        font-size: 0.85rem !important;
        line-height: 1.2 !important;
        font-variant-numeric: tabular-nums;
    }
    div[data-testid="stHorizontalBlock"] button p,
    div[data-testid="stHorizontalBlock"] button div,
    div[data-testid="stHorizontalBlock"] button span {
        white-space: nowrap !important;
        overflow: hidden !important;
        word-break: keep-all !important;
    }
    /* 左侧栏内列更紧凑 */
    div[data-testid="column"] {
        min-width: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 初始化库表 + 旧分类迁移
init_db()

# 每天首次打开自动同步外部日历（失败静默，不阻断页面）
if "ical_auto_tried" not in st.session_state:
    st.session_state.ical_auto_tried = True
    try:
        _auto = maybe_auto_sync_ical()
        if _auto and _auto.get("events"):
            st.session_state.ical_auto_msg = f"已自动同步外部日历 {_auto['events']} 条"
    except Exception:
        pass

# ==================== 固定 1:2 主布局（不可拖拽） ====================

panel_left, panel_right = st.columns([1, 2], gap="large")

with panel_left:
    st.title("📊 工作日志")
    st.caption("个人工时与完成事项追踪")

    # ==================== 日历格式日期选择（直接点击日期） ====================
    if "selected_date" not in st.session_state:
        st.session_state.selected_date = date.today()

    if "cal_view" not in st.session_state:
        st.session_state.cal_view = st.session_state.selected_date

    selected_date = st.session_state.selected_date
    view_date = st.session_state.cal_view

    # 当前选中日期
    weekday_cn = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    st.markdown(f"**📅 {selected_date.strftime('%Y-%m-%d')}** （{weekday_cn[selected_date.weekday()]}）")

    if st.button("📍 今天", key="goto_today", width="stretch"):
        st.session_state.selected_date = date.today()
        st.session_state.cal_view = date.today()
        st.rerun()

    # 月份导航
    nav_l, nav_c, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("◀", key="cal_prev", width="stretch"):
            y = view_date.year
            m = view_date.month
            if m == 1:
                y -= 1
                m = 12
            else:
                m -= 1
            st.session_state.cal_view = date(y, m, 1)
            st.rerun()
    with nav_r:
        if st.button("▶", key="cal_next", width="stretch"):
            y = view_date.year
            m = view_date.month
            if m == 12:
                y += 1
                m = 1
            else:
                m += 1
            st.session_state.cal_view = date(y, m, 1)
            st.rerun()
    with nav_c:
        st.markdown(f"<div style='text-align: center; font-weight: bold;'>{view_date.year}年{view_date.month}月</div>", unsafe_allow_html=True)

    # 本月外部日程（用于日历格子打标）
    _m_start = date(view_date.year, view_date.month, 1)
    if view_date.month == 12:
        _m_end = date(view_date.year + 1, 1, 1) - timedelta(days=1)
    else:
        _m_end = date(view_date.year, view_date.month + 1, 1) - timedelta(days=1)
    month_ext = get_ical_events(_m_start.isoformat(), _m_end.isoformat())
    # event_date -> 摘要列表
    ext_by_day: Dict[str, list] = {}
    if not month_ext.empty:
        for _, er in month_ext.iterrows():
            ext_by_day.setdefault(str(er["event_date"]), []).append(str(er["summary"] or ""))

    # 星期标题
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    header_cols = st.columns(7, gap="small")
    for i, wd in enumerate(weekdays):
        with header_cols[i]:
            st.markdown(
                f"<div style='text-align:center;font-size:0.72rem;white-space:nowrap;"
                f"overflow:hidden;line-height:1.2;'>{wd}</div>",
                unsafe_allow_html=True,
            )

    # 日历网格：日期按钮 + 格子内直接写节假日/日程简称
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(view_date.year, view_date.month)

    for week in month_days:
        day_cols = st.columns(7, gap="small")
        for i, day in enumerate(week):
            with day_cols[i]:
                if day == 0:
                    # 占位，保持各行高度一致
                    st.markdown(
                        "<div style='height:3.2rem'></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    d = date(view_date.year, view_date.month, day)
                    d_iso = d.isoformat()
                    is_selected = d == selected_date
                    summaries = ext_by_day.get(d_iso, [])
                    joined = " ".join(summaries)
                    short = short_cal_event_name(summaries[0]) if summaries else ""

                    # 按钮只显示日期数字
                    if st.button(
                        str(day),
                        key=f"cal_{d_iso}",
                        type="primary" if is_selected else "secondary",
                        width="stretch",
                        help=("；".join(summaries)[:120] if summaries else None),
                    ):
                        st.session_state.selected_date = d
                        st.session_state.cal_view = d
                        st.rerun()

                    # 日程名称直接画在格子里（按钮下方）
                    if short:
                        if "补班" in joined:
                            color = "#d97706"  # 补班橙
                        elif any(k in joined for k in ("假期", "假", "休")):
                            color = "#dc2626"  # 假期红
                        else:
                            color = "#2563eb"
                        full = html_lib.escape(summaries[0] if summaries else short)
                        shown = html_lib.escape(short)
                        st.markdown(
                            f"<div title='{full}' style='text-align:center;font-size:0.62rem;"
                            f"font-weight:600;color:{color};line-height:1.15;min-height:1.35em;"
                            f"margin-top:-0.35rem;overflow:hidden;white-space:nowrap;"
                            f"text-overflow:ellipsis;'>{shown}</div>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<div style='min-height:1.35em;margin-top:-0.35rem'></div>",
                            unsafe_allow_html=True,
                        )

    st.divider()

    # 快速统计
    st.markdown("**快速统计**")
    target = get_daily_target_hours()
    today_df = get_entries(selected_date.isoformat(), selected_date.isoformat())
    today_hours = today_df["hours"].sum() if not today_df.empty else 0

    col1, col2 = st.columns(2)
    col1.metric("今日工时", format_hours(today_hours), delta=f"目标 {target}h")
    col2.metric("条目数", len(today_df))

    b_ref, b_sync = st.columns(2)
    with b_ref:
        if st.button("🔄 刷新", width="stretch"):
            st.rerun()
    with b_sync:
        if st.button("⬇️ 同步日历", width="stretch", key="sync_ical_left"):
            enabled_subs = [s for s in list_ical_subscriptions() if s.get("enabled")]
            if not enabled_subs:
                st.warning("请先在设置里添加 ICS 订阅")
            else:
                with st.spinner("正在拉取外部日历…"):
                    result = sync_all_ical_subscriptions()
                if result["fail"]:
                    st.error(f"成功 {result['ok']}，失败 {result['fail']}")
                else:
                    st.success(f"已同步 {result['events']} 条")
                st.rerun()

with panel_right:
    # ==================== 主标签页 ====================
    tab_today, tab_week, tab_month, tab_history, tab_settings = st.tabs([
        "📅 今日", "📆 本周", "🗓️ 本月", "📋 历史编辑", "⚙️ 设置"
    ])

    # ==================== 今日页 ====================

    with tab_today:
        st.header(f"📅 {selected_date} 工作记录")

        # ==================== 新增工作记录 ====================
        st.subheader("新增工作记录")

        # 当前角色模板（研发 / 测试）→ 分类下拉 + 说明
        current_tpl_id = get_activity_template()
        current_tpl = get_template(current_tpl_id)
        form_categories = get_all_categories()
        if not form_categories:
            form_categories = template_categories(current_tpl_id)

        with st.expander(
            f"📋 {current_tpl['label']} 说明（{current_tpl['name']}模板 · 点开参考）",
            expanded=False,
        ):
            st.caption(f"当前模板：**{current_tpl['name']}**（可在「设置」中切换）")
            st.markdown(format_help_markdown(current_tpl_id))

        # 待保存列表（不用 st.form，避免分类异常时出现「Missing Submit Button」）
        pending_key = f"pending_items_{selected_date.isoformat()}"
        if pending_key not in st.session_state:
            st.session_state[pending_key] = []

        if not form_categories:
            form_categories = list(template_categories(current_tpl_id) or template_categories(TEMPLATE_DEV))
            if not form_categories:
                form_categories = ["其他"]
            st.warning("未读到分类配置，已使用默认列表。可到「设置」应用模板。")

        task_name = st.text_input(
            "任务名称 *",
            placeholder="简短任务名，如：修复规则引擎MQTT重复消费问题",
            key=f"task_name_{selected_date}",
        )
        activity_type = st.selectbox(
            f"{current_tpl['label']} *",
            options=form_categories,
            help=f"当前为「{current_tpl['name']}」模板；可在设置中切换研发/测试固定模板",
            key=f"activity_type_{selected_date}",
        )
        hours = st.number_input(
            "工作时长 (h)",
            min_value=0.1,
            max_value=12.0,
            value=1.5,
            step=0.5,
            format="%.1f",
            key=f"hours_{selected_date}",
        )
        work_content = st.text_area(
            "工作内容",
            height=70,
            placeholder="详细描述本次工作具体内容...",
            key=f"work_content_{selected_date}",
        )
        add_clicked = st.button(
            "➕ 添加到待保存列表",
            type="primary",
            width="stretch",
            key=f"add_pending_{selected_date}",
        )

        if add_clicked:
            if not task_name or not str(task_name).strip():
                st.warning("任务名称不能为空")
            else:
                st.session_state[pending_key].append({
                    "description": str(task_name).strip(),
                    "hours": float(hours),
                    "category": activity_type,
                    "notes": str(work_content).strip() if work_content else "",
                })
                st.success("已加入待保存列表")
                st.rerun()

        # 预览待保存列表
        if st.session_state[pending_key]:
            st.markdown(f"**待保存记录（{len(st.session_state[pending_key])} 条）**")

            pending_df = pd.DataFrame(st.session_state[pending_key]).copy()
            show_df = pending_df[["description", "hours", "category", "notes"]].rename(columns={
                "description": "任务名称",
                "hours": "时长(h)",
                "category": "活动类型",
                "notes": "工作内容",
            })
            st.dataframe(show_df, width="stretch", hide_index=True)

            b1, b2, b3 = st.columns([1.5, 1.5, 3])
            with b1:
                if st.button("✅ 保存全部到今日记录", type="primary", width="stretch"):
                    items = []
                    for it in st.session_state[pending_key]:
                        items.append({
                            "work_date": selected_date.isoformat(),
                            "description": it["description"],
                            "hours": it["hours"],
                            "category": it["category"],
                            "notes": it["notes"],
                        })
                    ids = add_work_items(items)
                    st.success(f"🎉 成功保存 {len(ids)} 条记录！")
                    st.session_state[pending_key] = []
                    st.rerun()

            with b2:
                if st.button("🗑️ 清空待保存列表", width="stretch"):
                    st.session_state[pending_key] = []
                    st.rerun()

            with b3:
                st.caption("可继续在上方表单添加更多条目，最后一次性保存。")
        else:
            st.caption("💡 **提示**：任务名称必填，活动类型参考上方说明。填好后点「添加」可连续追加多条。")

        st.divider()

        # 今日已保存记录
        st.subheader("📋 今日已记录")
        target_h = get_daily_target_hours()
        if not today_df.empty:
            display_df = today_df[["id", "description", "hours", "category", "notes"]].copy()
            display_df = display_df.rename(columns={
                "description": "任务名称", "hours": "时长(h)", "category": "分类", "notes": "备注",
            })
            st.dataframe(display_df, width="stretch", hide_index=True)

            total = float(today_df["hours"].sum())
            n_items = len(today_df)
            if total > target_h:
                st.warning(
                    f"今日合计 **{total:.1f}h**（已超过目标 {target_h:g}h） | {n_items} 条"
                )
            elif total > target_h * 0.9:
                st.info(
                    f"今日合计 **{total:.1f}h**（接近目标 {target_h:g}h） | {n_items} 条"
                )
            else:
                st.info(f"今日合计 **{total:.1f}h** / 目标 {target_h:g}h | {n_items} 条")

            # 快速改删（无需跳转历史页）
            with st.expander("✏️ 快速编辑 / 删除今日条目", expanded=False):
                id_opts = today_df["id"].tolist()
                labels = {
                    int(r.id): f"#{int(r.id)} · {r.description[:28]}（{r.hours}h）"
                    for r in today_df.itertuples()
                }
                pick = st.selectbox(
                    "选择条目",
                    options=id_opts,
                    format_func=lambda i: labels.get(int(i), str(i)),
                    key=f"today_edit_pick_{selected_date}",
                )
                row = today_df[today_df["id"] == pick].iloc[0]
                e_desc = st.text_input("任务名称", value=str(row["description"]), key=f"te_desc_{pick}")
                e_hours = st.number_input(
                    "时长(h)", min_value=0.1, max_value=12.0,
                    value=float(row["hours"]), step=0.5, key=f"te_h_{pick}",
                )
                cats = get_all_categories()
                cat_idx = cats.index(row["category"]) if row["category"] in cats else 0
                e_cat = st.selectbox("分类", options=cats, index=cat_idx, key=f"te_cat_{pick}")
                e_notes = st.text_input(
                    "备注", value=str(row["notes"] or ""), key=f"te_notes_{pick}",
                )
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("💾 保存修改", type="primary", width="stretch", key=f"te_save_{pick}"):
                        update_entry(
                            int(pick),
                            description=e_desc.strip(),
                            hours=float(e_hours),
                            category=e_cat,
                            notes=e_notes.strip(),
                        )
                        st.success("已更新")
                        st.rerun()
                with bc2:
                    if st.button("🗑️ 删除此条", width="stretch", key=f"te_del_{pick}"):
                        delete_entry(int(pick))
                        st.success("已删除")
                        st.rerun()
        else:
            st.info("今天还没有记录，赶快在上面的表单里添加吧！")

        # 外部订阅日程（当日）
        st.divider()
        st.subheader("📅 外部日历日程")
        today_cal = get_ical_events(selected_date.isoformat(), selected_date.isoformat())
        if today_cal.empty:
            st.caption("当日无外部日程（可在「设置」添加 ICS 订阅并同步）")
        else:
            show = today_cal.copy()
            show["时间"] = show.apply(
                lambda r: format_event_time(r["start_at"], r["end_at"], bool(r["all_day"])),
                axis=1,
            )
            st.dataframe(
                show[["时间", "summary", "source_name", "location"]].rename(
                    columns={
                        "summary": "日程",
                        "source_name": "来源日历",
                        "location": "地点",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    # ==================== 本周页 ====================

    with tab_week:
        st.header("📆 本周完成情况")

        week_start = get_week_start(selected_date)
        week_end = week_start + timedelta(days=6)

        st.caption(f"当前周：{week_start} ~ {week_end}")

        week_df = get_entries(week_start.isoformat(), week_end.isoformat())
        daily_sum = get_daily_summary(week_start.isoformat(), week_end.isoformat())

        # 指标
        total_h = week_df["hours"].sum() if not week_df.empty else 0
        work_days = len(daily_sum)
        avg = total_h / work_days if work_days > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("本周总工时", f"{total_h:.1f}h")
        c2.metric("工作天数", f"{work_days} 天")
        c3.metric("日均", f"{avg:.1f}h")

        # 每日柱图
        if not daily_sum.empty:
            st.bar_chart(daily_sum.set_index("work_date")["total_hours"], width="stretch")

        # 本周完成事项
        st.subheader("本周工作事项")
        if not week_df.empty:
            show_cols = ["work_date", "description", "hours", "category", "notes"]
            st.dataframe(
                week_df[show_cols].rename(columns={
                    "work_date": "日期", "description": "工作内容", "hours": "时长", "category": "分类", "notes": "备注"
                }),
                width="stretch", hide_index=True
            )
        else:
            st.info("本周暂无记录")

        st.divider()
        st.subheader("📅 本周外部日历")
        week_cal = get_ical_events(week_start.isoformat(), week_end.isoformat())
        if week_cal.empty:
            st.caption("本周无外部日程")
        else:
            wc = week_cal.copy()
            wc["时间"] = wc.apply(
                lambda r: format_event_time(r["start_at"], r["end_at"], bool(r["all_day"])),
                axis=1,
            )
            st.dataframe(
                wc[["event_date", "时间", "summary", "source_name", "location"]].rename(
                    columns={
                        "event_date": "日期",
                        "summary": "日程",
                        "source_name": "来源",
                        "location": "地点",
                    }
                ),
                width="stretch",
                hide_index=True,
            )

    # ==================== 本月页 ====================

    with tab_month:
        st.header("🗓️ 本月复盘")

        month_start = selected_date.replace(day=1)
        if selected_date.month == 12:
            month_end = selected_date.replace(year=selected_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = selected_date.replace(month=selected_date.month + 1, day=1) - timedelta(days=1)

        st.caption(f"{month_start.year}年{month_start.month}月")

        month_entries = get_entries(month_start.isoformat(), month_end.isoformat())
        month_daily = get_daily_summary(month_start.isoformat(), month_end.isoformat())
        cat_break = get_category_breakdown(month_start.isoformat(), month_end.isoformat())

        # 关键指标
        m_total = month_entries["hours"].sum() if not month_entries.empty else 0
        m_days = len(month_daily)
        m_avg = m_total / m_days if m_days > 0 else 0
        m_target = get_daily_target_hours() * m_days
        m_diff = m_total - m_target
        m_items = len(month_entries) if not month_entries.empty else 0

        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("本月总工时", f"{m_total:.1f}h", delta=f"{m_diff:+.1f}h vs 目标")
        cc2.metric("工作天数", f"{m_days}")
        cc3.metric("日均工时", f"{m_avg:.1f}h")
        cc4.metric("工作条目", m_items)

        # 趋势 + 分类
        col_left, col_right = st.columns([2, 1])
        with col_left:
            if not month_daily.empty:
                st.line_chart(month_daily.set_index("work_date")["total_hours"])
        with col_right:
            if not cat_break.empty:
                st.bar_chart(cat_break.set_index("category")["hours"])

        # Top 事项（按时长）
        st.subheader("本月工作事项（按时长）")
        if not month_entries.empty:
            top_m = month_entries.sort_values("hours", ascending=False).head(15)
            st.dataframe(
                top_m[["work_date", "description", "hours", "category"]].rename(
                    columns={"work_date": "日期", "description": "内容", "hours": "时长", "category": "分类"}
                ),
                width="stretch", hide_index=True
            )
        else:
            st.info("本月暂无记录")

        st.divider()
        st.subheader("📅 本月外部日历")
        month_cal = get_ical_events(month_start.isoformat(), month_end.isoformat())
        if month_cal.empty:
            st.caption("本月无外部日程")
        else:
            mc = month_cal.copy()
            mc["时间"] = mc.apply(
                lambda r: format_event_time(r["start_at"], r["end_at"], bool(r["all_day"])),
                axis=1,
            )
            st.dataframe(
                mc[["event_date", "时间", "summary", "source_name"]].rename(
                    columns={
                        "event_date": "日期",
                        "summary": "日程",
                        "source_name": "来源",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption(f"共 {len(month_cal)} 条外部日程")

        # 导出按钮
        st.divider()
        if st.button("📤 生成本月 Excel 复盘报告", type="primary", width="stretch"):
            month_str = f"{month_start.year}-{month_start.month:02d}"
            with st.spinner("正在生成专业 Excel 报告..."):
                out = generate_monthly_report(month_str)
                st.success(f"报告已生成：{out.name}")
                with open(out, "rb") as f:
                    st.download_button(
                        "⬇️ 下载 Excel 文件",
                        f.read(),
                        file_name=out.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

    # ==================== 历史编辑页（data_editor 专业版 - 变更检测 + 批量操作） ====================

    with tab_history:
        st.header("📋 历史记录查询与编辑")

        colf1, colf2 = st.columns([1, 1])
        with colf1:
            f_start = st.date_input("起始日期", value=selected_date - timedelta(days=14))
        with colf2:
            f_end = st.date_input("结束日期", value=selected_date)

        keyword = st.text_input("关键词过滤（描述/备注）", placeholder="输入关键词回车过滤")

        # 构建当前筛选的稳定 key
        filter_sig = f"{f_start}_{f_end}_{hash(keyword or '')}"
        editor_key = f"history_editor_{filter_sig}"
        original_key = f"history_original_{filter_sig}"

        # 清理旧的 history 相关 state（防止长期使用后 session_state 膨胀）
        for k in list(st.session_state.keys()):
            if k.startswith("history_") and filter_sig not in k:
                del st.session_state[k]

        # 查询最新数据
        hist_df = get_entries(f_start.isoformat(), f_end.isoformat())

        if keyword:
            mask = hist_df["description"].str.contains(keyword, case=False, na=False) | \
                   hist_df["notes"].str.contains(keyword, case=False, na=False)
            hist_df = hist_df[mask]

        if hist_df.empty:
            st.info("没有符合条件的记录")
            # 清理可能残留的旧状态
            for k in [editor_key, original_key]:
                if k in st.session_state:
                    del st.session_state[k]
        else:
            # 准备基础 DataFrame（用于 data_editor）
            base_df = hist_df[["id", "work_date", "description", "hours", "category", "notes"]].copy()
            base_df = base_df.rename(columns={
                "id": "ID",
                "work_date": "日期",
                "description": "工作内容",
                "hours": "时长(h)",
                "category": "分类",
                "notes": "备注",
            })
            base_df["删除?"] = False

            cats = get_all_categories()

            column_config = {
                "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                "日期": st.column_config.TextColumn("日期", disabled=True, width="small"),
                "工作内容": st.column_config.TextColumn("工作内容", width="large"),
                "时长(h)": st.column_config.NumberColumn("时长(h)", min_value=0.1, max_value=12.0, step=0.5, format="%.1f"),
                "分类": st.column_config.SelectboxColumn("分类", options=cats, required=True),
                "备注": st.column_config.TextColumn("备注"),
                "删除?": st.column_config.CheckboxColumn("删除?", help="勾选后保存时会永久删除该记录"),
            }

            # 首次加载这个筛选条件时，保存原始干净数据用于后续变更检测
            if original_key not in st.session_state:
                st.session_state[original_key] = base_df.drop(columns=["删除?"]).copy()

            original_df = st.session_state[original_key]

            # 渲染可编辑表格
            # 注意：edited_df 在当前 rerun 中始终是 DataFrame（Streamlit 保证）
            edited_df = st.data_editor(
                base_df,
                column_config=column_config,
                num_rows="fixed",
                width="stretch",
                key=editor_key,
                hide_index=True,
            )

            # ========== 实时变更统计（使用当前 edited_df 进行 diff） ==========
            to_update = 0
            to_delete = 0

            for _, row in edited_df.iterrows():
                rid = int(row["ID"])

                if row["删除?"]:
                    to_delete += 1
                    continue

                # 找到原始行进行比对
                orig_row = original_df[original_df["ID"] == rid]
                if orig_row.empty:
                    continue
                orig = orig_row.iloc[0]

                if (
                    str(row["工作内容"]).strip() != str(orig["工作内容"]).strip() or
                    float(row["时长(h)"]) != float(orig["时长(h)"]) or
                    row["分类"] != orig["分类"] or
                    str(row["备注"]).strip() != str(orig.get("备注", "")).strip()
                ):
                    to_update += 1

            # 漂亮的变更提示
            if to_update > 0 or to_delete > 0:
                st.info(f"📝 当前未保存变更：**将更新 {to_update} 条**，**将删除 {to_delete} 条**")
            else:
                st.caption(f"共 {len(hist_df)} 条记录 · 表格可直接编辑")

            # ========== 操作按钮区 ==========
            c1, c2, c3 = st.columns([1.1, 1.1, 2])
            with c1:
                if st.button("💾 保存所有更改", type="primary", width="stretch", disabled=(to_update + to_delete == 0)):
                    actual_updates = 0
                    actual_deletes = 0

                    # 直接使用当前 rerun 返回的 edited_df（最可靠，不会是 dict）
                    for _, row in edited_df.iterrows():
                        rid = int(row["ID"])

                        if row["删除?"]:
                            delete_entry(rid)
                            actual_deletes += 1
                            continue

                        # 找到原始数据进行精确比对
                        orig_row = original_df[original_df["ID"] == rid]
                        if orig_row.empty:
                            continue
                        orig = orig_row.iloc[0]

                        # 只有真正发生变化的才更新
                        if (
                            str(row["工作内容"]).strip() != str(orig["工作内容"]).strip() or
                            float(row["时长(h)"]) != float(orig["时长(h)"]) or
                            row["分类"] != orig["分类"] or
                            str(row["备注"]).strip() != str(orig.get("备注", "")).strip()
                        ):
                            update_entry(
                                rid,
                                description=str(row["工作内容"]).strip(),
                                hours=float(row["时长(h)"]),
                                category=row["分类"],
                                notes=str(row["备注"]).strip() if pd.notna(row["备注"]) else "",
                            )
                            actual_updates += 1

                    # 清理状态
                    for k in [editor_key, original_key]:
                        if k in st.session_state:
                            del st.session_state[k]

                    parts = []
                    if actual_updates:
                        parts.append(f"更新 {actual_updates} 条")
                    if actual_deletes:
                        parts.append(f"删除 {actual_deletes} 条")
                    st.success("、".join(parts) + " 完成！")
                    st.rerun()

            with c2:
                if st.button("🗑️ 重置所有删除勾选（会丢失其他未保存的编辑）", width="stretch"):
                    for k in [editor_key, original_key]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()

            with c3:
                if st.button("🔄 重新加载此筛选数据（丢弃未保存编辑）", width="stretch"):
                    for k in [editor_key, original_key]:
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()

            st.caption("💡 提示：编辑后上方会实时显示变更数量。只有真正修改过的记录才会被写入数据库。")

    # ==================== 设置页 ====================

    with tab_settings:
        st.header("⚙️ 设置")

        st.subheader("活动类型模板")
        st.caption("固定两套模板：**研发人员** / **测试人员**。切换后填报下拉与说明文案会一起更换。")

        tpl_id = get_activity_template()
        tpl_options = {
            TEMPLATE_DEV: ROLE_TEMPLATES[TEMPLATE_DEV]["name"],
            TEMPLATE_QA: ROLE_TEMPLATES[TEMPLATE_QA]["name"],
        }
        # radio 用显示名，映射回 id
        name_to_id = {v: k for k, v in tpl_options.items()}
        chosen_name = st.radio(
            "选择角色模板",
            options=list(tpl_options.values()),
            index=list(tpl_options.keys()).index(tpl_id) if tpl_id in tpl_options else 0,
            horizontal=True,
            key="tpl_radio",
        )
        preview = get_template(name_to_id[chosen_name])
        st.markdown(f"**{preview['name']}** 包含：")
        st.write(" · ".join(preview["categories"]))

        c_apply, c_hint = st.columns([1, 2])
        with c_apply:
            if st.button("✅ 应用此模板", type="primary", width="stretch"):
                apply_activity_template(name_to_id[chosen_name])
                st.success(f"已切换为「{chosen_name}」模板")
                st.rerun()
        with c_hint:
            st.caption("应用后会重置为该模板的标准 7 类（覆盖当前分类列表）。")

        with st.expander(f"预览「{preview['name']}」类型说明", expanded=False):
            st.markdown(format_help_markdown(preview["id"]))

        st.divider()
        st.subheader("分类管理（可微调）")
        st.caption(
            f"当前模板：**{get_template(get_activity_template())['name']}**。"
            "一般直接用模板即可；若需临时增删类名可在此编辑（不改变模板说明文案）。"
        )
        current_cats = get_all_categories()
        cat_text = st.text_area("分类列表（每行一个）", value="\n".join(current_cats), height=150)
        if st.button("保存分类"):
            new_cats = [c.strip() for c in cat_text.splitlines() if c.strip()]
            if new_cats:
                set_categories(new_cats)
                st.success("分类已更新，填报页下拉框将使用最新列表")
                st.rerun()
        if st.button("↩ 恢复为当前模板标准分类"):
            apply_activity_template(get_activity_template())
            st.success("已恢复为当前模板标准 7 类")
            st.rerun()

        st.divider()
        st.subheader("每日目标工时")
        target_h = st.number_input("标准每日工时", min_value=1.0, max_value=16.0, value=get_daily_target_hours(), step=0.5)
        if st.button("保存目标"):
            set_config("daily_target_hours", str(target_h))
            st.success(f"目标已设为 {target_h}h/天")
            st.rerun()

        st.divider()
        st.subheader("📅 订阅外部日历（iCal / ICS）")
        st.caption(
            "粘贴 Google / Outlook / 企业日历等提供的 **ICS 订阅地址**，"
            "同步后会在左侧、今日/本周/本月中显示。支持 `https://` 与 `webcal://`。"
        )

        sub_name = st.text_input("显示名称", placeholder="例如：团队会议 / 节假日", key="ical_sub_name")
        sub_url = st.text_input(
            "ICS 订阅链接 *",
            placeholder="https://calendar.ics 或 webcal://...",
            key="ical_sub_url",
        )
        sub_color = st.color_picker("标记颜色", value="#2563eb", key="ical_sub_color")
        add_sub = st.button("➕ 添加并同步", type="primary", width="stretch", key="ical_sub_add")

        if add_sub:
            if not sub_url or not str(sub_url).strip():
                st.warning("请填写 ICS 订阅链接")
            else:
                url = normalize_ics_url(str(sub_url).strip())
                name = (sub_name or "").strip() or "外部日历"
                try:
                    sid = add_ical_subscription(name, url, color=sub_color)
                    with st.spinner("正在拉取日历…"):
                        events = sync_subscription_from_url(
                            url,
                            range_start=date.today() - timedelta(days=60),
                            range_end=date.today() + timedelta(days=120),
                        )
                        n = replace_ical_events(sid, events)
                    st.success(f"已订阅「{name}」，同步 {n} 条日程")
                    st.rerun()
                except Exception as e:  # noqa: BLE001
                    try:
                        subs_now = list_ical_subscriptions()
                        hit = next((s for s in subs_now if s["url"] == url), None)
                        if hit:
                            mark_ical_sync_error(hit["id"], str(e))
                    except Exception:
                        pass
                    st.error(f"订阅失败：{e}")

        subs = list_ical_subscriptions()
        if not subs:
            st.info("还没有外部订阅。从日历服务复制「秘密地址 / iCal 链接」粘贴到上方即可。")
        else:
            st.markdown("**已订阅列表**")
            for sub in subs:
                c1, c2, c3, c4 = st.columns([2.2, 0.8, 1.2, 1.0])
                with c1:
                    status = "🟢" if sub.get("enabled") else "⚪"
                    err = sub.get("last_error") or ""
                    sync_t = sub.get("last_sync") or "从未同步"
                    st.markdown(
                        f"{status} **{sub['name']}**  \n"
                        f"<span style='font-size:0.8rem;color:#666;word-break:break-all;'>{sub['url']}</span>  \n"
                        f"<span style='font-size:0.8rem;'>上次同步：{sync_t} · {sub.get('event_count', 0)} 条"
                        + (f" · ⚠️ {err[:80]}" if err else "")
                        + "</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    en = st.checkbox(
                        "启用",
                        value=bool(sub.get("enabled")),
                        key=f"ical_en_{sub['id']}",
                    )
                    if en != bool(sub.get("enabled")):
                        set_ical_subscription_enabled(sub["id"], en)
                        st.rerun()
                with c3:
                    if st.button("同步", key=f"ical_sync_{sub['id']}", width="stretch"):
                        try:
                            with st.spinner("同步中…"):
                                events = sync_subscription_from_url(
                                    sub["url"],
                                    range_start=date.today() - timedelta(days=60),
                                    range_end=date.today() + timedelta(days=120),
                                )
                                n = replace_ical_events(sub["id"], events)
                            st.success(f"已同步 {n} 条")
                            st.rerun()
                        except Exception as e:  # noqa: BLE001
                            mark_ical_sync_error(sub["id"], str(e))
                            st.error(str(e))
                with c4:
                    if st.button("删除", key=f"ical_del_{sub['id']}", width="stretch"):
                        delete_ical_subscription(sub["id"])
                        st.rerun()

            if st.button("⬇️ 同步全部已启用订阅", type="primary", width="stretch"):
                with st.spinner("同步全部…"):
                    result = sync_all_ical_subscriptions()
                if result["fail"]:
                    st.warning(
                        f"成功 {result['ok']} 个，失败 {result['fail']} 个，事件 {result['events']} 条"
                    )
                    for err in result["errors"]:
                        st.caption(err)
                else:
                    st.success(f"全部成功：{result['ok']} 个源，{result['events']} 条事件")
                st.rerun()

        st.divider()
        st.subheader("数据备份")
        st.caption("备份文件保存在 reports/，默认只保留最近 10 份。也可直接复制 data/worklog.db。")
        if st.button("📦 一键备份当前数据库", type="primary"):
            dst = backup_database(ROOT / "reports", keep=10)
            st.success(f"备份完成：{dst.name}")

        # 启动时自动同步提示
        if st.session_state.get("ical_auto_msg"):
            st.info(st.session_state.pop("ical_auto_msg"))

# 页脚
st.divider()
st.caption("工作日志 v1.1 · 本地 SQLite · 研发/测试双模板 · ICS 订阅 · 数据仅本机")
