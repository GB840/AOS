"""
Superpowers — "流程大于提示词"的技能框架。
Think → Plan → Code → Test → Review 五步门控流程。
确保每个动作都经过系统化思考, 避免 AI "瞎干活"。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

GATE_QUESTIONS = {
    "think": [
        "这个任务的核心目标是什么?",
        "有哪些约束条件?",
        "需要什么输入数据?",
        "预期输出是什么格式?",
    ],
    "plan": [
        "分几步完成? 每步的输入输出是什么?",
        "哪些步骤可以并行?",
        "有哪些风险点? 如何处理?",
        "需要调用哪些工具/子智能体?",
    ],
    "code": [
        "核心逻辑是什么?",
        "边界条件处理了吗?",
        "错误处理完善吗?",
        "是否需要测试?",
    ],
    "test": [
        "正常输入能跑通吗?",
        "边界值测试通过吗?",
        "错误输入会崩溃吗?",
        "输出格式符合预期吗?",
    ],
    "review": [
        "代码有没有安全问题?",
        "性能是否可接受?",
        "有没有更好的实现方式?",
        "是否需要文档/注释?",
    ],
}


class SuperpowersSkill(Skill):
    """五步门控流程框架.

    Think  → 理解任务, 明确约束
    Plan   → 拆解步骤, 评估风险
    Code   → 实现核心逻辑
    Test   → 验证正确性
    Review → 安全检查 + 优化建议

    每步都是一个"门控"(gate), 必须通过当前门控才能进入下一步.
    可以用于任何复杂任务的质量保证.

    Usage:
        result = registry.execute("superpowers", {
            "task": "写一个 WebSocket 服务器",
            "step": "think"  # 或 plan/code/test/review
        })
    """

    def __init__(self):
        meta = SkillMeta(
            name="superpowers",
            description="五步门控流程框架 (Think→Plan→Code→Test→Review), 确保每个动作都经过系统化思考",
            version="1.0.0",
            tags=["process", "quality", "gate-control", "engineering"],
            capabilities=["process_gating", "quality_assurance", "task_decomposition"],
            category="autonomous-ai-agents",
        )
        super().__init__(meta)

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", context.get("message", ""))
        step = context.get("step", "think").lower()
        previous_result = context.get("previous_result", {})

        if not task:
            return {"success": False, "error": "缺少 task 字段"}

        if step not in GATE_QUESTIONS:
            return {
                "success": False,
                "error": f"未知步骤 '{step}', 有效步骤: {list(GATE_QUESTIONS.keys())}",
            }

        questions = GATE_QUESTIONS[step]
        pipeline = list(GATE_QUESTIONS.keys())
        current_index = pipeline.index(step)
        next_step = pipeline[current_index + 1] if current_index + 1 < len(pipeline) else None

        return {
            "success": True,
            "step": step,
            "task": task,
            "gate_questions": questions,
            "pipeline": pipeline,
            "current_index": current_index,
            "next_step": next_step,
            "previous_result": previous_result,
            "instruction": (
                f"请回答以下 {len(questions)} 个门控问题:\n"
                + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))
                + f"\n\n完成后返回: {{'step': '{step}', 'answers': [...], 'ready_for_next': true}}"
                + (f"\n下一步: {next_step}" if next_step else "\n所有步骤完成!")
            ),
            "all_steps": [
                {"name": s, "status": "done" if pipeline.index(s) < current_index else ("current" if s == step else "pending")}
                for s in pipeline
            ],
            "timestamp": datetime.now().isoformat(),
        }