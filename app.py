#!/usr/bin/env python3
"""
工作日志管理系统 - Streamlit 主应用
运行：streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import calendar
from pathlib import Path
import sys
import shutil

# 确保能导入本地模块
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from db import (
    init_db, add_work_items, get_entries, update_entry, delete_entry,
    get_daily_summary, get_weekly_completed, get_category_breakdown,
    get_highlights, get_all_categories, set_categories,
    get_daily_target_hours, set_config
)
try:
    from scripts.generate_report import generate_monthly_report
except ImportError:
    # 允许直接从项目根运行
    sys.path.insert(0, str(ROOT / "scripts"))
    from generate_report import generate_monthly_report

st.set_page_config(
    page_title="工作日志",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 初始化
init_db()

# ==================== 辅助函数 ====================

def get_week_start(d: date) -> date:
    """返回所在周的周一"""
    return d - timedelta(days=d.weekday())

def format_hours(h: float) -> str:
    return f"{h:.1f}h"

def status_badge(status: str) -> str:
    if status == "done":
        return "✅ 已完成"
    elif status == "in_progress":
        return "🔄 进行中"
    else:
        return "📌 计划中"


# 状态显示名称 <-> 内部值 的双向映射（用于 data_editor）
STATUS_DISPLAY = {
    "done": "✅ 已完成",
    "in_progress": "🔄 进行中",
    "planned": "📌 计划中",
}
STATUS_OPTIONS = list(STATUS_DISPLAY.values())
STATUS_REVERSE = {v: k for k, v in STATUS_DISPLAY.items()}

# 开发活动类型（根据部门QA更新的规则，7大类）
ACTIVITY_TYPES = [
    "日常事务类",
    "问题治理类",
    "开发实现类",
    "方案设计类",
    "技术攻关类",
    "项目管理类",
    "赋能建设类",
]

ACTIVITY_HELP = {
    "日常事务类": "杂事、行政、常规沟通。例会、周报、活动、行政事务等。不直接产生技术价值。",
    "问题治理类": "救火 + 维护现状。Bug修复、故障排查、部署发布、值班、日常巡检。路径明确，目标是恢复或维持系统正常运行。",
    "开发实现类": "按图施工。有明确需求/设计文档，按着实现功能、写代码、执行测试等。",
    "方案设计类": "出方案、做设计。目标明确但实现路径要自己分析判断，产出是技术方案、架构设计、选型等。",
    "技术攻关类": "硬骨头。没有成熟方案的技术难题，需要深度研究、突破瓶颈、性能优化等。",
    "项目管理类": "当项目经理。协调多人多任务、项目计划、进度跟踪、风险/资源管理、跨团队推动交付。",
    "赋能建设类": "给团队充电。不直接产业务，但建设长期能力：培训新人、知识库、流程规范、工具平台等。",
}

# ==================== 侧边栏 ====================

with st.sidebar:
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

    if st.button("📍 今天", key="goto_today", use_container_width=True):
        st.session_state.selected_date = date.today()
        st.session_state.cal_view = date.today()
        st.rerun()

    # 月份导航
    nav_l, nav_c, nav_r = st.columns([1, 2, 1])
    with nav_l:
        if st.button("◀", key="cal_prev", use_container_width=True):
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
        if st.button("▶", key="cal_next", use_container_width=True):
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

    # 星期标题
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    header_cols = st.columns(7, gap="small")
    for i, wd in enumerate(weekdays):
        with header_cols[i]:
            st.caption(f"<div style='text-align:center; font-size: 0.75rem;'>{wd}</div>", unsafe_allow_html=True)

    # 日历网格 - 直接点击
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(view_date.year, view_date.month)

    for week in month_days:
        day_cols = st.columns(7, gap="small")
        for i, day in enumerate(week):
            with day_cols[i]:
                if day == 0:
                    st.write(" ")
                else:
                    d = date(view_date.year, view_date.month, day)
                    is_selected = d == selected_date
                    is_today = d == date.today()

                    label = str(day)
                    if is_today and not is_selected:
                        label = f"*{day}*"

                    if st.button(
                        label,
                        key=f"cal_{d.isoformat()}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state.selected_date = d
                        st.rerun()

    st.divider()

    # 快速统计
    st.markdown("**快速统计**")
    target = get_daily_target_hours()
    today_df = get_entries(selected_date.isoformat(), selected_date.isoformat())
    today_hours = today_df["hours"].sum() if not today_df.empty else 0

    col1, col2 = st.columns(2)
    col1.metric("今日工时", format_hours(today_hours), delta=f"目标 {target}h")
    col2.metric("条目数", len(today_df))

    if st.button("🔄 刷新数据", use_container_width=True):
        st.rerun()

# ==================== 主标签页 ====================

tab_today, tab_week, tab_month, tab_history, tab_settings = st.tabs([
    "📅 今日", "📆 本周", "🗓️ 本月", "📋 历史编辑", "⚙️ 设置"
])

# ==================== 今日页 ====================

with tab_today:
    st.header(f"📅 {selected_date} 工作记录")

    # ==================== 新增工作记录 ====================
    st.subheader("新增工作记录")

    # 活动类型说明
    with st.expander("📋 开发活动类型 说明（点开参考QA规则）"):
        for atype, desc in ACTIVITY_HELP.items():
            st.markdown(f"**{atype}**：{desc}")

    # 待保存列表
    pending_key = f"pending_items_{selected_date.isoformat()}"
    if pending_key not in st.session_state:
        st.session_state[pending_key] = []

    with st.form("add_work_item_form", clear_on_submit=True):
        task_name = st.text_input(
            "任务名称 *",
            placeholder="简短任务名，如：修复规则引擎MQTT重复消费问题",
        )

        activity_type = st.selectbox(
            "开发活动类型 *",
            options=ACTIVITY_TYPES,
            help="根据部门QA规则选择（上方有详细说明）",
        )

        hours = st.number_input(
            "工作时长 (h)", min_value=0.1, max_value=12.0, value=1.5, step=0.5, format="%.1f"
        )

        work_content = st.text_area(
            "工作内容",
            height=70,
            placeholder="详细描述本次工作具体内容...",
        )

        add_clicked = st.form_submit_button("➕ 添加到待保存列表", type="primary", use_container_width=True)

    if add_clicked:
        if not task_name or not str(task_name).strip():
            st.warning("任务名称不能为空")
        else:
            st.session_state[pending_key].append({
                "description": str(task_name).strip(),
                "hours": float(hours),
                "category": activity_type,
                "status": "done",
                "notes": str(work_content).strip() if work_content else "",
                "is_highlight": False,
            })

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
        st.dataframe(show_df, use_container_width=True, hide_index=True)

        b1, b2, b3 = st.columns([1.5, 1.5, 3])
        with b1:
            if st.button("✅ 保存全部到今日记录", type="primary", use_container_width=True):
                items = []
                for it in st.session_state[pending_key]:
                    items.append({
                        "work_date": selected_date.isoformat(),
                        "description": it["description"],
                        "hours": it["hours"],
                        "category": it["category"],
                        "status": it["status"],
                        "notes": it["notes"],
                        "is_highlight": it["is_highlight"],
                    })
                ids = add_work_items(items)
                st.success(f"🎉 成功保存 {len(ids)} 条记录！")
                st.session_state[pending_key] = []
                st.rerun()

        with b2:
            if st.button("🗑️ 清空待保存列表", use_container_width=True):
                st.session_state[pending_key] = []
                st.rerun()

        with b3:
            st.caption("可继续在上方表单添加更多条目，最后一次性保存。")
    else:
        st.caption("💡 **提示**：任务名称必填，活动类型参考上方说明。填好后点「添加」可连续追加多条。")

    st.divider()

    # 今日已保存记录
    st.subheader("📋 今日已记录")
    if not today_df.empty:
        display_df = today_df[["id", "description", "hours", "category", "status", "notes", "is_highlight"]].copy()
        display_df["status"] = display_df["status"].apply(status_badge)
        display_df["亮点"] = display_df["is_highlight"].apply(lambda x: "★" if x else "")
        display_df = display_df.rename(columns={
            "description": "工作内容", "hours": "时长(h)", "category": "分类", "notes": "备注"
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        total = today_df["hours"].sum()
        done_cnt = (today_df["status"] == "done").sum()
        st.info(f"今日合计 **{total:.1f}h** | 已完成 {done_cnt}/{len(today_df)} 项")
    else:
        st.info("今天还没有记录，赶快在上面的表单里添加吧！")

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
        st.bar_chart(daily_sum.set_index("work_date")["total_hours"], use_container_width=True)

    # 本周完成事项
    st.subheader("本周已完成事项（亮点优先）")
    completed = get_weekly_completed(week_start.isoformat())
    if not completed.empty:
        show_cols = ["work_date", "description", "hours", "category", "notes"]
        st.dataframe(
            completed[show_cols].rename(columns={
                "work_date": "日期", "description": "工作内容", "hours": "时长", "category": "分类", "notes": "备注"
            }),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("本周暂无已完成记录")

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
    highlights = get_highlights(month_start.isoformat(), month_end.isoformat())

    # 关键指标
    m_total = month_entries["hours"].sum() if not month_entries.empty else 0
    m_days = len(month_daily)
    m_avg = m_total / m_days if m_days > 0 else 0
    m_target = get_daily_target_hours() * m_days
    m_diff = m_total - m_target

    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric("本月总工时", f"{m_total:.1f}h", delta=f"{m_diff:+.1f}h vs 目标")
    cc2.metric("工作天数", f"{m_days}")
    cc3.metric("日均工时", f"{m_avg:.1f}h")
    cc4.metric("本月亮点", len(highlights))

    # 趋势 + 分类
    col_left, col_right = st.columns([2, 1])
    with col_left:
        if not month_daily.empty:
            st.line_chart(month_daily.set_index("work_date")["total_hours"])
    with col_right:
        if not cat_break.empty:
            st.bar_chart(cat_break.set_index("category")["hours"])

    # Top 完成
    st.subheader("本月亮点 / 重要完成事项")
    if not highlights.empty:
        st.dataframe(
            highlights[["work_date", "description", "hours", "category"]].rename(
                columns={"work_date": "日期", "description": "内容", "hours": "时长", "category": "分类"}
            ),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("本月暂无标记为亮点的记录（可在录入时勾选）")

    # 导出按钮
    st.divider()
    if st.button("📤 生成本月 Excel 复盘报告", type="primary", use_container_width=True):
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
        base_df = hist_df[["id", "work_date", "description", "hours", "category", "status", "notes", "is_highlight"]].copy()
        base_df = base_df.rename(columns={
            "id": "ID",
            "work_date": "日期",
            "description": "工作内容",
            "hours": "时长(h)",
            "category": "分类",
            "status": "状态",
            "notes": "备注",
            "is_highlight": "亮点",
        })
        base_df["删除?"] = False

        # 转成用户友好的状态显示名
        base_df["状态"] = base_df["状态"].map(STATUS_DISPLAY).fillna(base_df["状态"])

        cats = get_all_categories()

        column_config = {
            "ID": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "日期": st.column_config.TextColumn("日期", disabled=True, width="small"),
            "工作内容": st.column_config.TextColumn("工作内容", width="large"),
            "时长(h)": st.column_config.NumberColumn("时长(h)", min_value=0.1, max_value=12.0, step=0.5, format="%.1f"),
            "分类": st.column_config.SelectboxColumn("分类", options=cats, required=True),
            "状态": st.column_config.SelectboxColumn("状态", options=STATUS_OPTIONS),
            "备注": st.column_config.TextColumn("备注"),
            "亮点": st.column_config.CheckboxColumn("亮点 ★"),
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
            use_container_width=True,
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

            new_status = STATUS_REVERSE.get(row["状态"], row["状态"])
            if (
                str(row["工作内容"]).strip() != str(orig["工作内容"]).strip() or
                float(row["时长(h)"]) != float(orig["时长(h)"]) or
                row["分类"] != orig["分类"] or
                new_status != orig["状态"] or
                str(row["备注"]).strip() != str(orig.get("备注", "")).strip() or
                bool(row["亮点"]) != bool(orig["亮点"])
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
            if st.button("💾 保存所有更改", type="primary", use_container_width=True, disabled=(to_update + to_delete == 0)):
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

                    new_status = STATUS_REVERSE.get(row["状态"], row["状态"])

                    # 只有真正发生变化的才更新
                    if (
                        str(row["工作内容"]).strip() != str(orig["工作内容"]).strip() or
                        float(row["时长(h)"]) != float(orig["时长(h)"]) or
                        row["分类"] != orig["分类"] or
                        new_status != orig["状态"] or
                        str(row["备注"]).strip() != str(orig.get("备注", "")).strip() or
                        bool(row["亮点"]) != bool(orig["亮点"])
                    ):
                        update_entry(
                            rid,
                            description=str(row["工作内容"]).strip(),
                            hours=float(row["时长(h)"]),
                            category=row["分类"],
                            status=new_status,
                            notes=str(row["备注"]).strip() if pd.notna(row["备注"]) else "",
                            is_highlight=bool(row["亮点"]),
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
            if st.button("🗑️ 重置所有删除勾选（会丢失其他未保存的编辑）", use_container_width=True):
                for k in [editor_key, original_key]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

        with c3:
            if st.button("🔄 重新加载此筛选数据（丢弃未保存编辑）", use_container_width=True):
                for k in [editor_key, original_key]:
                    if k in st.session_state:
                        del st.session_state[k]
                st.rerun()

        st.caption("💡 提示：编辑后上方会实时显示变更数量。只有真正修改过的记录才会被写入数据库。")

# ==================== 设置页 ====================

with tab_settings:
    st.header("⚙️ 设置")

    st.subheader("分类管理")
    current_cats = get_all_categories()
    cat_text = st.text_area("分类列表（每行一个）", value="\n".join(current_cats), height=150)
    if st.button("保存分类"):
        new_cats = [c.strip() for c in cat_text.splitlines() if c.strip()]
        if new_cats:
            set_categories(new_cats)
            st.success("分类已更新")
            st.rerun()

    st.divider()
    st.subheader("每日目标工时")
    target_h = st.number_input("标准每日工时", min_value=1.0, max_value=16.0, value=get_daily_target_hours(), step=0.5)
    if st.button("保存目标"):
        set_config("daily_target_hours", str(target_h))
        st.success(f"目标已设为 {target_h}h/天")
        st.rerun()

    st.divider()
    st.subheader("数据备份")
    if st.button("📦 一键备份当前数据库"):
        backup_dir = ROOT / "reports"
        backup_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = backup_dir / f"worklog_backup_{ts}.db"
        shutil.copy(ROOT / "data/worklog.db", dst)
        st.success(f"备份完成：{dst.name}")

    st.caption("提示：直接复制 data/worklog.db 即可完整迁移数据。")

# 页脚
st.divider()
st.caption("工作日志 v1.0 · 本地 SQLite 存储 · 数据永不离开你的电脑")
