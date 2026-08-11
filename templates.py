#!/usr/bin/env python3
"""
工时活动类型固定模板：研发 / 测试 两套。
设置里切换模板后，填报下拉与说明文案一起切换。
"""

from __future__ import annotations

from typing import Any, Dict, List

# 模板 ID
TEMPLATE_DEV = "dev"
TEMPLATE_QA = "qa"

ROLE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    TEMPLATE_DEV: {
        "id": TEMPLATE_DEV,
        "name": "研发人员",
        "label": "开发活动类型",
        "categories": [
            "日常事务类",
            "问题治理类",
            "开发实现类",
            "方案设计类",
            "技术攻关类",
            "项目管理类",
            "赋能建设类",
        ],
        # 每项：简短说明（兼容旧版展示）+ 可选结构化字段
        "help": {
            "日常事务类": {
                "summary": "杂事、行政、常规沟通。例会、周报、活动、行政事务等。不直接产生技术价值。",
                "purpose": "处理与具体技术交付关系不大的日常行政与团队事务。",
                "examples": "例会、周报、各种活动、行政事务。",
                "not_for": "跟项目交付强相关的技术工作（应归到对应技术类）。",
            },
            "问题治理类": {
                "summary": "救火 + 维护现状。Bug修复、故障排查、部署发布、值班、日常巡检。路径明确，目标是恢复或维持系统正常运行。",
                "purpose": "处理已知问题或维持系统稳定，路径相对明确。",
                "examples": "Bug 修复、故障排查、部署发布、值班、日常巡检。",
                "not_for": "从零设计方案、无成熟路径的技术硬骨头（应归技术攻关/方案设计）。",
            },
            "开发实现类": {
                "summary": "按图施工。有明确需求/设计文档，按着实现功能、写代码、执行测试等。",
                "purpose": "按已有需求或设计落地功能与代码。",
                "examples": "按需求开发功能、写代码、执行单测/联调。",
                "not_for": "还要先出方案选型的；特别疑难无现成路径的。",
            },
            "方案设计类": {
                "summary": "出方案、做设计。目标明确但实现路径要自己分析判断，产出是技术方案、架构设计、选型等。",
                "purpose": "产出技术方案/架构/选型，而不是直接写业务代码交付。",
                "examples": "技术方案、架构设计、组件选型。",
                "not_for": "已有方案只负责实现的；纯救火修 Bug 的。",
            },
            "技术攻关类": {
                "summary": "硬骨头。没有成熟方案的技术难题，需要深度研究、突破瓶颈、性能优化等。",
                "purpose": "攻克没有成熟方案的技术难题。",
                "examples": "深度性能优化、疑难问题定位、新技术预研突破。",
                "not_for": "常规 Bug 修复、按设计实现功能。",
            },
            "项目管理类": {
                "summary": "当项目经理。协调多人多任务、项目计划、进度跟踪、风险/资源管理、跨团队推动交付。",
                "purpose": "协调多人多任务，推动项目按计划交付。",
                "examples": "项目计划、进度跟踪、风险/资源管理、跨团队推动。",
                "not_for": "自己独立写代码实现功能的；组织级流程/平台建设的。",
            },
            "赋能建设类": {
                "summary": "给团队充电。不直接产业务，但建设长期能力：培训新人、知识库、流程规范、工具平台等。",
                "purpose": "提升团队长期效率，而非当前项目交付。",
                "examples": "带教、知识库、流程规范、工具平台、系统性学习。",
                "not_for": "日常项目里的普通沟通；按已有方案直接开发的。",
            },
        },
    },
    TEMPLATE_QA: {
        "id": TEMPLATE_QA,
        "name": "测试人员",
        "label": "测试活动类型",
        "categories": [
            "用例设计",
            "用例执行",
            "环境准备",
            "缺陷跟进",
            "协作响应",
            "赋能建设",
            "日常事务",
        ],
        "help": {
            "用例设计": {
                "summary": "还没有现成的测试方案/用例，需要先想清楚「测什么、怎么测」，把方案和用例写出来。",
                "purpose": "还没有现成的测试方案/用例，需要你先想清楚“测什么、怎么测”，把方案和用例写出来。",
                "examples": "新功能来了，你拆测试点、写用例、定测试策略。",
                "not_for": "已经有用例直接跑的；单纯搭环境的。",
            },
            "用例执行": {
                "summary": "已有现成用例或方案，按着跑测试，给出通过/失败/缺陷结论。",
                "purpose": "已经有现成的用例或方案，你按着跑测试，最后给出通过/失败/缺陷结论。",
                "examples": "首轮测试、回归、数据对比、稳定性监控、写测试报告。",
                "not_for": "还要先设计用例的；单纯复现和跟 Bug 的。",
            },
            "环境准备": {
                "summary": "测试跑不起来，先把环境和数据搞定，让测试能顺利执行。",
                "purpose": "测试跑不起来，先把环境和数据搞定，让测试能顺利执行。",
                "examples": "搭测试环境、造测试数据、环境坏了去修。",
                "not_for": "环境已经好了直接测的；做自动化框架建设的。",
            },
            "缺陷跟进": {
                "summary": "已发现明确 Bug，推动闭环：复现、协助定位、验证修复、reopen 跟踪。",
                "purpose": "已经发现了明确的 Bug，你负责推动它闭环（复现、协助定位、验证修复、reopen 跟踪）。",
                "examples": "复现 Bug、帮开发定位、验证修复结果。",
                "not_for": "测试过程中顺手记结果的；特别疑难、需要深度攻关才能定位的问题。",
            },
            "协作响应": {
                "summary": "不是闷头干活，而是沟通、对齐、等依赖、处理变更——核心是协同推进。",
                "purpose": "不是你自己闷头干活，而是需要跟别人沟通、对齐、等依赖、处理变更。核心是“协同推进”。",
                "examples": "评审会、需求变更后重测、等外部依赖、进度/风险/资源协调。",
                "not_for": "自己独立做测试决策和设计的；做组织级流程建设的。",
            },
            "赋能建设": {
                "summary": "不为当前项目交付，而为团队以后更高效的长期投入。",
                "purpose": "不是为了当前这个项目交付，而是为了让团队以后更高效的长期投入。",
                "examples": "带教、建规范、知识库沉淀、自动化工具开发、AI 工具验证、系统性学习、维护必保功能清单（不绑具体项目时）。",
                "not_for": "日常项目里的普通沟通；按已有方案直接执行测试的。",
            },
            "日常事务": {
                "summary": "跟具体项目无关、也套不进上面任何一类的日常行政/团队事务。",
                "purpose": "跟具体项目没关系、也套不进上面任何一类的日常行政/团队事务。",
                "examples": "例会、周报、各种活动、行政事务。",
                "not_for": "跟项目相关的沟通协调（应归到「协作响应」）。",
            },
        },
    },
}


def get_template(template_id: str) -> Dict[str, Any]:
    return ROLE_TEMPLATES.get(template_id) or ROLE_TEMPLATES[TEMPLATE_DEV]


def list_templates() -> List[Dict[str, str]]:
    return [
        {"id": t["id"], "name": t["name"]}
        for t in ROLE_TEMPLATES.values()
    ]


def template_categories(template_id: str) -> List[str]:
    return list(get_template(template_id)["categories"])


def template_help(template_id: str) -> Dict[str, Dict[str, str]]:
    return dict(get_template(template_id)["help"])


def format_help_markdown(template_id: str) -> str:
    """生成说明区 Markdown。"""
    t = get_template(template_id)
    lines = []
    for i, cat in enumerate(t["categories"], 1):
        h = t["help"].get(cat) or {}
        lines.append(f"### {i}. {cat}")
        if h.get("purpose"):
            lines.append(f"**干什么用的：** {h['purpose']}")
        elif h.get("summary"):
            lines.append(f"**说明：** {h['summary']}")
        if h.get("examples"):
            lines.append(f"**典型场景：** {h['examples']}")
        if h.get("not_for"):
            lines.append(f"**别往这里填：** {h['not_for']}")
        lines.append("")
    return "\n".join(lines)
