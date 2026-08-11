#!/usr/bin/env python3
"""
初始化工作日志数据库。

用法：
  python3 scripts/init_db.py           # 仅建表 + 默认配置（不插演示数据）
  python3 scripts/init_db.py --seed    # 额外插入当前模板下的示例记录（空库时）
"""

import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import (
    init_db,
    add_work_items,
    get_conn,
    set_categories,
    get_all_categories,
    DEFAULT_CATEGORIES,
    get_activity_template,
    apply_activity_template,
)


def build_seed_entries() -> list:
    """按当前分类模板生成约两周示例（分类名与模板一致）。"""
    cats = get_all_categories() or list(DEFAULT_CATEGORIES)
    # 取若干分类轮换
    c = (cats + cats)[:8]
    today = date.today()
    # 从两周前的周一开始
    start = today - timedelta(days=today.weekday() + 14)
    entries = []
    samples = [
        ("完成模块接口联调与自测", 3.5, 0),
        ("参与需求/方案评审会", 1.5, 1),
        ("排查线上问题并验证修复", 2.0, 2),
        ("整理本周进展与风险", 1.0, 3),
        ("编写/更新设计或测试文档", 2.5, 4),
        ("团队分享或知识库沉淀", 1.5, 5),
        ("环境准备与数据构造", 2.0, 6),
        ("回归验证关键路径", 3.0, 0),
    ]
    d = start
    for i in range(10):
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        for j in range(2):
            desc, hours, ci = samples[(i + j) % len(samples)]
            entries.append({
                "work_date": d.isoformat(),
                "description": f"{desc}（示例）",
                "hours": hours,
                "category": c[ci % len(c)],
                "notes": "init_db --seed 生成的示例数据，可删",
            })
        d += timedelta(days=1)
    return entries


def main():
    seed = "--seed" in sys.argv
    print("🚀 初始化工作日志数据库...")
    init_db()
    print("✅ 表结构 / 默认配置就绪")

    # 确保分类为当前默认模板
    apply_activity_template(get_activity_template() or "dev")
    print(f"✅ 分类模板：{get_all_categories()}")

    if seed:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM entries")
        n = cur.fetchone()[0]
        conn.close()
        if n > 0:
            print(f"ℹ️  库中已有 {n} 条记录，跳过示例数据插入")
        else:
            inserted = add_work_items(build_seed_entries())
            print(f"✅ 已插入 {len(inserted)} 条示例记录")
    else:
        print("ℹ️  未插入示例数据（需要时加 --seed）")

    print("\n🎉 完成。运行：./run.sh  或  streamlit run app.py")


if __name__ == "__main__":
    main()
