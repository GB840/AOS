"""AOS 元调度引擎 (L3.5 顶层 DISPATCH/POLICY/TRUST 决策层)。

负责:
1) 意图分层分类 → 路由到 L1/L2/L3/L3.5 工作流;
2) 任务优先级查询;
3) L3.5 自修改提案(受人工门控,绝不自动改代码)。

源码重建说明:原 engine.py 丢失(仅 .pyc 残留),无法被 Python 3.13/3.14 加载。
本文件按调用点契约(brain.py + main.py + tests + meta_orchestrator.proto)
于 2026-07-19 重建。规则采用纯启发式(无 LLM 调用),满足 API 契约但简化
决策逻辑——原版可能有更复杂的 LLM 分层,重建版以"最小可工作诚实实现"为
原则;后续可按 docs/evolution_roadmap 增强决策(诚实:不假装跑 LLM 分层)。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


_DEFAULT_EVOLUTION_LOG = str(
    Path(__file__).resolve().parents[2] / "data" / "evolution" / "evolution_log.jsonl"
)


# 分层语义(启发式 → 不调 LLM):
# - L1: 简单对话/问答(hi / 你好 / 是什么)
# - L2: 多轮任务/检索(搜一下 / 查一下 / 帮我找)
# - L3: 多步编排(生成 / 编写 / 自动化 / 工作流)
# - L3.5: 元调度/自修改/策略调整(自己改 / 调整策略 / 元层)
_INTENT_RULES: list[tuple[str, str, str, str]] = [
    # (正则, layer, complexity, workflow_id)
    (
        r"(自己改|自修改|调整策略|元层|meta|self.?modif|propose)",
        "L3.5",
        "high",
        "meta_orchestration",
    ),
    (
        r"(工作流|workflow|自动化|automation|编排|orchestrat)",
        "L3",
        "high",
        "workflow_orchestration",
    ),
    (
        r"(生成|编写|创建|generate|create|write|build|开发)",
        "L3",
        "medium",
        "content_generation",
    ),
    (
        r"(搜|查|找|search|find|lookup|query)",
        "L2",
        "medium",
        "search_retrieve",
    ),
    (
        r"(你好|hi|hello|嗨|是什么|什么是|explain)",
        "L1",
        "low",
        "simple_chat",
    ),
]


def classify_intent(intent: str) -> tuple[str, str, str]:
    """纯函数意图分类 → (layer, complexity, workflow_id)。

    不调 LLM、不依赖外部状态,启发式规则匹配。
    默认 fallback: L2 / medium / general_task。

    注:这是重建版的简化实现,原版可能基于 LLM 分层;为诚实,这里不伪装跑 LLM。
    后续若接入真实分层模型,见 docs/evolution_roadmap。
    """
    if not intent:
        return ("L2", "medium", "general_task")
    text = intent.lower()
    for pattern, layer, complexity, wf in _INTENT_RULES:
        if re.search(pattern, text):
            return (layer, complexity, wf)
    return ("L2", "medium", "general_task")


class MetaOrchestratorEngine:
    """元调度引擎 — 实例化后供 brain.py / main.py 调用。"""

    def __init__(self, evolution_log_path: Optional[str] = None):
        self._evolution_log = evolution_log_path or os.environ.get(
            "AOS_EVOLUTION_LOG", _DEFAULT_EVOLUTION_LOG
        )
        os.makedirs(os.path.dirname(self._evolution_log), exist_ok=True)
        logger.info("MetaOrchestratorEngine ready (L3.5 dispatch)")

    def route_intent(
        self,
        intent: str,
        user_id: str = "system",
        project_id: str = "",
        trace_id: str = "",
    ) -> dict:
        """意图分层路由。

        返回:
            {layer, complexity, workflow_id, priority, persona_config,
             trace_id, user_id, project_id, intent, ts}
        """
        layer, complexity, wf = classify_intent(intent)
        # 优先级: L1=1, L2=2, L3=3, L3.5=4
        priority_map = {"L1": 1, "L2": 2, "L3": 3, "L3.5": 4}
        priority = priority_map.get(layer, 2)
        # persona_config: 按 layer 给不同人格配置(最小可工作)
        persona_map = {
            "L1": "default",
            "L2": "diligent",
            "L3": "architect",
            "L3.5": "meta",
        }
        result = {
            "layer": layer,
            "complexity": complexity,
            "workflow_id": wf,
            "priority": priority,
            "persona_config": persona_map.get(layer, "default"),
            "trace_id": trace_id or f"tr-{uuid.uuid4().hex[:16]}",
            "user_id": user_id,
            "project_id": project_id,
            "intent": intent,
            "ts": time.time(),
        }
        # 落 evolution_log(与 verify_db_layer.py / test_database.py 期望一致)
        self._append_evolution_log({"type": "route_intent", **result})
        return result

    def query_priority(self, task_id: str) -> int:
        """查询任务优先级(结合历史指纹)。

        简化实现:从 evolution_log 反查最近一次 route_intent 的 priority。
        未查到返回 2 (L2 默认)。
        """
        if not os.path.exists(self._evolution_log):
            return 2
        try:
            with open(self._evolution_log, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return 2
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            # 优先按 trace_id 匹配,再按 task_id 字段
            if entry.get("trace_id") == task_id or entry.get("task_id") == task_id:
                return int(entry.get("priority", 2))
        return 2

    def propose_self_modification(
        self, intent: str, proposer: str = "aos"
    ) -> dict:
        """捕获 L3.5 自修改意图 → 生成受人工门控的提案。

        铁律:绝不自动改代码;仅生成提案,等 /api/approvals 人工批准后才执行。
        """
        proposal = {
            "proposal_id": f"prop-{uuid.uuid4().hex[:12]}",
            "type": "self_modification",
            "intent": intent,
            "proposer": proposer,
            "status": "pending_approval",  # 必须人工批准
            "risk_level": "high",           # L3.5 自修改默认高风险
            "ts": time.time(),
            "approved": False,
            "executed": False,
        }
        self._append_evolution_log({"type": "propose", **proposal})
        logger.info(
            "MetaOrchestratorEngine: self-modification proposed (waiting approval): %s",
            proposal["proposal_id"],
        )
        return proposal

    def _append_evolution_log(self, entry: dict) -> None:
        """落 evolution_log.jsonl。"""
        try:
            with open(self._evolution_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("evolution_log append failed: %s", e)
