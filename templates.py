"""Small, fixed activity templates used by the worklog."""

TEMPLATE_DEV = "dev"
TEMPLATE_QA = "qa"
DEFAULT_TEMPLATE_ID = TEMPLATE_DEV

ROLE_TEMPLATES = {
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
    },
}


def get_template(template_id: str) -> dict:
    return ROLE_TEMPLATES.get(template_id, ROLE_TEMPLATES[DEFAULT_TEMPLATE_ID])


def template_categories(template_id: str) -> list[str]:
    return list(get_template(template_id)["categories"])
