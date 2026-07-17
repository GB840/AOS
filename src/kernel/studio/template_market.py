"""工作流模板市场 —— Studio 的预置模板。

设计原则：
- 开箱即用：用户来了就能用，不用从零开始
- 覆盖常见场景：代码、内容、数据、营销
- 可定制：模板只是起点，用户可以改
"""
from __future__ import annotations

import logging
from typing import List

from .workflow_models import Workflow
from .workflow_store import WorkflowStore, get_workflow_store

logger = logging.getLogger(__name__)


# 预置模板定义
_BUILTIN_TEMPLATES = [
    {
        "name": "内容营销视频",
        "description": "输入主题，自动搜索素材、写脚本、生成短视频。适合做抖音/小红书/B站内容。",
        "category": "marketing",
        "tags": ["视频", "营销", "内容创作", "自动化"],
        "steps": [
            {"name": "搜索素材", "capability": "web.search", "in_from": "initial"},
            {"name": "生成脚本", "capability": "inference.llm", "in_from": "previous"},
            {"name": "生成视频", "capability": "media.video", "in_from": "previous"},
        ],
    },
    {
        "name": "代码生成与执行",
        "description": "输入需求，自动写代码并运行验证。适合快速验证想法。",
        "category": "coding",
        "tags": ["代码", "编程", "自动化", "Python"],
        "steps": [
            {"name": "生成代码", "capability": "inference.llm", "in_from": "initial"},
            {"name": "执行代码", "capability": "action.code_exec", "in_from": "previous"},
        ],
    },
    {
        "name": "网页摘要助手",
        "description": "输入 URL，自动抓取网页内容并生成摘要。适合快速了解长文。",
        "category": "productivity",
        "tags": ["摘要", "阅读", "效率", "网页"],
        "steps": [
            {"name": "抓取网页", "capability": "web.fetch", "in_from": "initial"},
            {"name": "生成摘要", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "竞品情报分析",
        "description": "输入竞品名称，自动搜索全网讨论、分析优劣势、生成报告。",
        "category": "marketing",
        "tags": ["竞品", "分析", "市场", "情报"],
        "steps": [
            {"name": "搜索竞品信息", "capability": "web.search", "in_from": "initial"},
            {"name": "抓取详情", "capability": "web.fetch", "in_from": "previous"},
            {"name": "分析报告", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "数据分析报告",
        "description": "输入数据文件路径，自动分析数据、生成图表、写报告。",
        "category": "data",
        "tags": ["数据", "分析", "报告", "可视化"],
        "steps": [
            {"name": "读取数据", "capability": "action.file_access", "in_from": "initial"},
            {"name": "数据分析", "capability": "action.code_exec", "in_from": "previous"},
            {"name": "生成报告", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "每日新闻摘要",
        "description": "搜索今日热点新闻，生成个性化摘要。每天早上跑一遍。",
        "category": "productivity",
        "tags": ["新闻", "摘要", "日报", "资讯"],
        "steps": [
            {"name": "搜索新闻", "capability": "web.search", "in_from": "initial"},
            {"name": "抓取详情", "capability": "web.fetch", "in_from": "previous"},
            {"name": "生成摘要", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "论文速读",
        "description": "输入论文标题或关键词，自动搜索、抓取、生成中文解读。适合科研人员快速了解前沿。",
        "category": "research",
        "tags": ["论文", "科研", "学术", "摘要"],
        "steps": [
            {"name": "搜索论文", "capability": "web.search", "in_from": "initial"},
            {"name": "抓取论文内容", "capability": "web.fetch", "in_from": "previous"},
            {"name": "中文解读", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "小红书爆款文案",
        "description": "输入产品或主题，自动生成小红书风格种草文案，含标题、正文、标签。",
        "category": "marketing",
        "tags": ["小红书", "文案", "种草", "社交媒体"],
        "steps": [
            {"name": "搜索参考", "capability": "web.search", "in_from": "initial"},
            {"name": "生成文案", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "邮件智能回复",
        "description": "输入邮件内容，自动生成礼貌专业的回复草稿。支持多种语气风格。",
        "category": "productivity",
        "tags": ["邮件", "办公", "效率", "写作"],
        "steps": [
            {"name": "理解邮件", "capability": "inference.llm", "in_from": "initial"},
            {"name": "生成回复", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "代码审查助手",
        "description": "输入代码文件路径，自动检查 bug、性能问题、风格问题，给出审查报告。",
        "category": "coding",
        "tags": ["代码审查", "质量", "Bug", "最佳实践"],
        "steps": [
            {"name": "读取代码", "capability": "action.file_access", "in_from": "initial"},
            {"name": "代码审查", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "翻译与润色",
        "description": "输入文本，自动翻译并润色成地道表达。支持中英互译、多语言。",
        "category": "productivity",
        "tags": ["翻译", "润色", "语言", "写作"],
        "steps": [
            {"name": "初译", "capability": "inference.llm", "in_from": "initial"},
            {"name": "润色优化", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "SEO 文章生成",
        "description": "输入关键词，自动生成 SEO 优化的长文，含标题结构、关键词密度、元描述。",
        "category": "marketing",
        "tags": ["SEO", "写作", "博客", "流量"],
        "steps": [
            {"name": "关键词调研", "capability": "web.search", "in_from": "initial"},
            {"name": "生成大纲", "capability": "inference.llm", "in_from": "previous"},
            {"name": "生成全文", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "产品需求文档",
        "description": "输入产品想法，自动生成完整的 PRD 文档，含用户故事、功能列表、原型描述。",
        "category": "product",
        "tags": ["产品", "PRD", "需求", "文档"],
        "steps": [
            {"name": "竞品分析", "capability": "web.search", "in_from": "initial"},
            {"name": "生成 PRD", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "学习计划生成",
        "description": "输入想学习的技能，自动生成个性化学习路径，含资源推荐和时间规划。",
        "category": "education",
        "tags": ["学习", "教育", "成长", "规划"],
        "steps": [
            {"name": "搜索学习资源", "capability": "web.search", "in_from": "initial"},
            {"name": "生成学习计划", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
    {
        "name": "图片描述生成",
        "description": "输入图片路径，自动生成详细的文字描述和标签。适合电商、内容管理。",
        "category": "media",
        "tags": ["图像", "VLM", "描述", "标签"],
        "steps": [
            {"name": "读取图片", "capability": "action.file_access", "in_from": "initial"},
            {"name": "图像理解", "capability": "multimodal.vlm", "in_from": "previous"},
        ],
    },
    {
        "name": "会议纪要生成",
        "description": "输入会议录音或文字记录，自动生成结构化纪要，含决议、待办、责任人。",
        "category": "productivity",
        "tags": ["会议", "纪要", "办公", "效率"],
        "steps": [
            {"name": "语音转写", "capability": "audio.stt", "in_from": "initial"},
            {"name": "生成纪要", "capability": "inference.llm", "in_from": "previous"},
        ],
    },
]


def ensure_builtin_templates(store: WorkflowStore = None) -> int:
    """确保预置模板已安装。返回新安装的数量。"""
    store = store or get_workflow_store()
    installed = 0

    for tmpl in _BUILTIN_TEMPLATES:
        # 检查是否已存在
        existing = store.list(search=tmpl["name"], is_template=True, limit=1)
        if existing:
            continue  # 已有，跳过

        # 创建模板
        wf = store.create(
            name=tmpl["name"],
            description=tmpl["description"],
            author="aos_system",
        )
        wf.category = tmpl["category"]
        wf.tags = tmpl["tags"]
        wf.is_template = True

        # 添加步骤
        for step_def in tmpl["steps"]:
            wf.add_step(
                capability=step_def["capability"],
                name=step_def.get("name", ""),
                in_from=step_def.get("in_from", "previous"),
            )

        store.save(wf)
        installed += 1
        logger.info("安装模板: %s", tmpl["name"])

    if installed > 0:
        logger.info("共安装 %d 个预置模板", installed)

    return installed


def list_templates(store: WorkflowStore = None, category: str = "",
                   search: str = "") -> List[dict]:
    """列出所有模板。"""
    store = store or get_workflow_store()
    return store.list(is_template=True, category=category, search=search)


def get_template(template_id: str, store: WorkflowStore = None) -> Workflow | None:
    """获取一个模板。"""
    store = store or get_workflow_store()
    wf = store.get(template_id)
    if wf and wf.is_template:
        return wf
    return None


def use_template(template_id: str, new_name: str = "", store: WorkflowStore = None,
                 author: str = "user") -> Workflow | None:
    """基于模板创建一个新的工作流（副本）。"""
    store = store or get_workflow_store()
    tmpl = get_template(template_id, store)
    if not tmpl:
        return None

    name = new_name or f"{tmpl.name}（副本）"
    new_wf = store.create(name=name, description=tmpl.description, author=author)
    new_wf.category = tmpl.category
    new_wf.tags = list(tmpl.tags) if tmpl.tags else []

    # 复制步骤
    for step in tmpl.steps:
        new_wf.add_step(
            capability=step.capability,
            name=step.name,
            in_from=step.in_from,
            prompt=step.prompt,
            payload=dict(step.payload) if step.payload else {},
        )

    store.save(new_wf)
    return new_wf
