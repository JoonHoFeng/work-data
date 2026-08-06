#!/usr/bin/env python3
"""
初始化工作日志数据库 + 插入高质量示例数据（2 周跨度）
运行：python3 scripts/init_db.py
"""

import sys
from pathlib import Path

# 允许从项目根直接运行
sys.path.insert(0, str(Path(__file__).parent.parent))

from db import init_db, add_work_items, get_conn, set_categories, get_all_categories

SEED_CATEGORIES = ["开发", "会议", "测试", "联调", "文档", "学习", "其他"]

# 真实感示例数据（模拟 ThingsBoard IoT 平台维护工作）
SEED_ENTRIES = [
    # 2026-05-18 (周一)
    {"work_date": "2026-05-18", "description": "修复 ThingsBoard 规则引擎中 MQTT 消息重复消费问题", "hours": 3.5, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-18", "description": "与 QA 联调 Edge 设备影子同步场景", "hours": 2.0, "category": "联调", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-18", "description": "部门周会 - 平台 Q2 迭代规划", "hours": 1.5, "category": "会议", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-18", "description": "撰写 Cassandra 集群扩容方案文档", "hours": 1.0, "category": "文档", "status": "in_progress", "is_highlight": 0},

    # 2026-05-19
    {"work_date": "2026-05-19", "description": "完成规则引擎性能压测脚本（JMeter + Python 客户端）", "hours": 4.0, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-19", "description": "参加 ThingsBoard 社区会议（线上）", "hours": 1.0, "category": "会议", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-19", "description": "Review PR #1247 - CoAP 适配层重构", "hours": 2.0, "category": "开发", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-19", "description": "学习 Kafka 事务消息在 IoT 场景的应用", "hours": 1.0, "category": "学习", "status": "done", "is_highlight": 0},

    # 2026-05-20
    {"work_date": "2026-05-20", "description": "修复 Edge 端 SQLite 数据库升级导致的迁移失败", "hours": 3.0, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-20", "description": "测试 10 万设备并发连接场景", "hours": 3.5, "category": "测试", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-20", "description": "客户现场问题复现（远程协助）", "hours": 1.5, "category": "联调", "status": "in_progress", "is_highlight": 0},

    # 2026-05-21
    {"work_date": "2026-05-21", "description": "实现 Redis 缓存预热策略，降低冷启动延迟 40%", "hours": 4.5, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-21", "description": "技术分享：ThingsBoard 3.x 到 4.1 升级踩坑记录", "hours": 1.5, "category": "学习", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-21", "description": "整理本周完成事项并更新项目看板", "hours": 1.0, "category": "其他", "status": "done", "is_highlight": 0},

    # 2026-05-22
    {"work_date": "2026-05-22", "description": "Kafka 消费组重平衡问题排查与优化", "hours": 2.5, "category": "开发", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-22", "description": "与运维讨论生产环境监控告警规则", "hours": 1.5, "category": "会议", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-22", "description": "撰写 5 月平台稳定性复盘报告（初稿）", "hours": 2.0, "category": "文档", "status": "in_progress", "is_highlight": 0},
    {"work_date": "2026-05-22", "description": "参加产品需求评审会", "hours": 1.5, "category": "会议", "status": "done", "is_highlight": 0},

    # 2026-05-25 (跳过周末)
    {"work_date": "2026-05-25", "description": "Elasticsearch 索引模板优化，查询耗时下降 60%", "hours": 3.0, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-25", "description": "联调新接入的 Modbus 网关设备", "hours": 2.5, "category": "联调", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-25", "description": "修复前端 Angular 16 升级后规则链画布渲染异常", "hours": 2.0, "category": "开发", "status": "done", "is_highlight": 0},

    # 2026-05-26
    {"work_date": "2026-05-26", "description": "完成 4.1.2 版本发布前集成测试 checklist", "hours": 3.5, "category": "测试", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-26", "description": "与客户确认 6 月上旬试点部署方案", "hours": 1.5, "category": "会议", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-26", "description": "准备 ThingsBoard Edge 容器化部署手册 v2", "hours": 2.0, "category": "文档", "status": "done", "is_highlight": 1},

    # 2026-05-27
    {"work_date": "2026-05-27", "description": "定位并修复生产环境 3 台 Edge 节点内存泄漏", "hours": 4.0, "category": "开发", "status": "done", "is_highlight": 1},
    {"work_date": "2026-05-27", "description": "内部 Code Review 3 个 PR", "hours": 1.5, "category": "开发", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-27", "description": "学习 Prometheus + Grafana 在 IoT 监控的最佳实践", "hours": 1.5, "category": "学习", "status": "done", "is_highlight": 0},

    # 2026-05-28
    {"work_date": "2026-05-28", "description": "重构 CoAP 消息编解码模块，提升可维护性", "hours": 3.0, "category": "开发", "status": "in_progress", "is_highlight": 0},
    {"work_date": "2026-05-28", "description": "准备 5 月底项目进度汇报 PPT", "hours": 2.0, "category": "其他", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-28", "description": "测试新版本 Edge 固件 OTA 升级流程", "hours": 2.0, "category": "测试", "status": "done", "is_highlight": 0},
    {"work_date": "2026-05-28", "description": "部门复盘会 - 5 月平台稳定性改进点", "hours": 1.0, "category": "会议", "status": "done", "is_highlight": 0},
]


def main():
    print("🚀 初始化工作日志数据库...")

    init_db()
    print("✅ 表结构创建完成")

    # 设置分类
    set_categories(SEED_CATEGORIES)
    print(f"✅ 默认分类已设置：{get_all_categories()}")

    # 插入种子数据
    inserted = add_work_items(SEED_ENTRIES)
    print(f"✅ 已插入 {len(inserted)} 条示例工作记录（2026-05-18 ~ 2026-05-28）")

    # 打印简单统计
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(hours) FROM entries")
    count, total_h = cur.fetchone()
    print(f"📊 当前数据库共 {count} 条记录，总工时 {total_h:.1f}h")

    conn.close()
    print("\n🎉 初始化完成！现在可以运行：streamlit run app.py")


if __name__ == "__main__":
    main()
