"""
Skill Creator — AOS 元技能。
用自然语言描述工作流程, 自动生成可复用的 SKILL.md。
对应 Hermes 的 skill_manager_tool.py, 但集成到 AOS 的 SkillRegistry 中。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Skill, SkillMeta, SkillRegistry

logger = logging.getLogger(__name__)

SKILL_TEMPLATE = """---
name: {name}
description: "{description}"
version: 1.0.0
author: AOS
license: MIT
tags: [{tags}]
platforms: [python]
capabilities: [{capabilities}]
---

# {name}

## Overview
{description}

## When to Use
{when_to_use}

## Process
1. **Input**: {input_desc}
2. **Execute**: {execute_desc}
3. **Output**: {output_desc}

## Integration
- AOS SkillRegistry: `registry.execute("{name}", context)`
- DeerFlow Scheduler: `scheduler.submit_task("{name}", input_data)`

## Pitfalls
{pitfalls}

## Verification Checklist
- [ ] Skill can execute with minimal context
- [ ] Output format matches schema
- [ ] Error handling catches common failures
"""


class SkillCreator(Skill):
    """元技能: 根据自然语言描述创建新技能.

    流程: 用户描述 → LLM 分析 → 生成 SKILL.md → 注册到 SkillRegistry.
    可以创建采集器专属任务、数据处理流水线、报告生成模板等.

    Usage:
        result = registry.execute("skill-creator", {
            "name": "arxiv-paper-collector",
            "description": "每日采集 cs.AI 领域最新论文摘要",
            "workflow": "搜索 arXiv API → 过滤 cs.AI → 提取摘要 → 存为 Markdown"
        })
    """

    def __init__(self, llm_router=None):
        meta = SkillMeta(
            name="skill-creator",
            description="元技能: 用自然语言描述工作流程, 自动生成可复用的 SKILL.md 技能文件",
            version="1.0.0",
            tags=["meta", "self-evolution", "skill-generation"],
            capabilities=["skill_creation", "workflow_distillation", "self_evolution"],
            category="autonomous-ai-agents",
        )
        super().__init__(meta)
        self._llm_router = llm_router
        self._output_dir = Path("D:/AOS/src/skills/generated")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        name = context.get("name", "")
        description = context.get("description", "")
        workflow = context.get("workflow", context.get("message", ""))

        if not name or not workflow:
            return {
                "success": False,
                "error": "Missing required fields: name, workflow (or message)",
            }

        skill_name = name.lower().replace(" ", "-").replace("_", "-")
        tags = context.get("tags", [])
        capabilities = context.get("capabilities", ["custom"])
        when_to_use = context.get("when_to_use", f"当你需要自动执行 '{description}' 时")
        input_desc = context.get("input_desc", workflow.split("→")[0].strip() if "→" in workflow else "接收任务参数")
        execute_desc = context.get("execute_desc", workflow)
        output_desc = context.get("output_desc", "返回执行结果")
        pitfalls = context.get("pitfalls", "- 网络请求可能超时\n- 输入格式需校验\n- 大文件处理注意内存")
        model = context.get("model", "")
        dry_run = context.get("dry_run", False)

        # ---- 如果提供了 LLM Router, 用 LLM 增强技能描述 ----
        enhanced_description = description
        if self._llm_router and description:
            try:
                prompt = (
                    f"优化以下技能描述, 使其更清晰简洁(不超过120字):\n{description}\n\n"
                    f"工作流: {workflow}"
                )
                result = self._llm_router.chat(
                    [{"role": "user", "content": prompt}],
                    task_type=None,
                    model_override=model,
                )
                if result.get("success"):
                    enhanced_description = result["content"].strip()[:200]
            except Exception as exc:
                logger.warning("LLM 增强描述失败, 使用原始描述: %s", exc)

        # ---- 生成 SKILL.md 内容 ----
        skill_md = SKILL_TEMPLATE.format(
            name=skill_name,
            description=enhanced_description,
            tags=", ".join(tags),
            capabilities=", ".join(capabilities),
            when_to_use=when_to_use,
            input_desc=input_desc,
            execute_desc=execute_desc,
            output_desc=output_desc,
            pitfalls=pitfalls,
        )

        if dry_run:
            return {
                "success": True,
                "skill_name": skill_name,
                "description": enhanced_description,
                "skill_md": skill_md,
                "mode": "dry_run",
            }

        # ---- 写入文件 ----
        filepath = self._output_dir / f"{skill_name}.md"
        filepath.write_text(skill_md, encoding="utf-8")

        # ---- 注册到 SkillRegistry ----
        registry = SkillRegistry()
        if registry.has(skill_name):
            registry.unregister(skill_name)

        # 动态创建简单技能包装器
        new_skill = _GeneratedSkill(
            meta=SkillMeta(
                name=skill_name,
                description=enhanced_description,
                tags=tags,
                capabilities=capabilities,
                category=context.get("category", "generated"),
            ),
            skill_md=skill_md,
        )
        registry.register(new_skill)

        logger.info("新技能已创建并注册: %s → %s", skill_name, filepath)

        return {
            "success": True,
            "skill_name": skill_name,
            "description": enhanced_description,
            "file": str(filepath),
            "registered": True,
            "created_at": datetime.now().isoformat(),
        }


class _GeneratedSkill(Skill):
    """由 SkillCreator 动态生成的技能包装器."""

    def __init__(self, meta: SkillMeta, skill_md: str):
        super().__init__(meta)
        self._skill_md = skill_md

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "message": f"[{self.name}] 这是动态生成的技能, 请查看完整定义",
            "skill_md": self._skill_md,
            "suggestion": "将此技能部署到具体子智能体后即可正式使用",
        }

    def to_skill_md(self) -> str:
        return self._skill_md