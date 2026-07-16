"""
AOS v5.0 — L3.5 元调度引擎 (真实实现)

将原先 gRPC 桩 (固定返回 echo_workflow) 升级为可解释的三层进化路由:

  RouteIntent  意图 -> 层(L1/L2/L3/L3.5) + 复杂度评分 + 工作流 + 成本-精度人设
  QueryPriority 任务 -> 优先级 (结合层与复杂度)
  InjectPersona  用户/项目 -> 人设配置 (初稿小模型 / 定稿大模型 的成本-精度策略)

设计原则:
  - 纯函数 classify_intent() 可单测、不依赖 IO
  - 引擎对数据库写入用 best-effort，DB 不可用时仍返回路由结果 (不阻断服务)
  - 路由决策落库 evolution_log，供后续自演进/回放使用
"""

import json
import logging
import queue
import threading
import re
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 意图 -> 层 的规则 (按顺序匹配，先命中先得)
# 注意: L3.5 的 "meta" 必须用 \b 词边界，否则会误匹配 metadata / parameter /
# automate 等词，把普通意图错判为 L3.5 元调度。
LAYER_RULES: list[Tuple[str, str]] = [
    (r"进化|自修改|自我修改|元调度|元编排|self[.\s_-]?modif|evolve|\bmeta\b|反思", "L3.5"),
    (r"协商|协调|多智能体|multi[.\s_-]?agent|negotiat|coordinate|主辅|角色", "L3"),
    (r"构建|开发|代码|code|build|implement|工程|部署|debug|测试", "L2"),
    (r"搜索|研究|调研|research|search|总结|summary|翻译|问答|extract", "L1"),
]

# 每层对应的默认工作流
WORKFLOWS: Dict[str, str] = {
    "L1": "wf_research_001",
    "L2": "wf_engineering_001",
    "L3": "wf_negotiation_001",
    "L3.5": "wf_meta_evolution_001",
}

# 成本-精度策略: 初稿用小模型(省成本)，定稿用大模型(保精度)
DRAFT_MODELS = {"L1": "mini", "L2": "mini", "L3": "standard", "L3.5": "standard"}
FINAL_MODELS = {"L1": "standard", "L2": "pro", "L3": "pro", "L3.5": "pro"}

# 层基础优先级
LAYER_BASE_PRIORITY = {"L1": 3, "L2": 5, "L3": 7, "L3.5": 9}


def classify_intent(intent: str) -> Tuple[str, int, str]:
    """纯函数: 将意图文本分类到进化层，并给出复杂度(1-10)与工作流。

    Returns:
        (layer, complexity, workflow_id)
    """
    text = (intent or "").strip()
    layer = "L1"  # 默认层
    for pattern, lyr in LAYER_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            layer = lyr
            break

    # 复杂度: 长度 + 多目标连词 + 技术关键词
    complexity = 1
    complexity += len(text) // 25
    complexity += text.count(",") + text.count("，")
    complexity += text.count("且") + text.count("并") + text.count("和")
    complexity += len(re.findall(r"api|数据库|并发|分布式|安全|合规|gb/?z", text, re.I))
    complexity = max(1, min(10, complexity))

    return layer, complexity, WORKFLOWS[layer]


class MetaOrchestratorEngine:
    """L3.5 元调度引擎 (线程安全)。

    进化日志 (evolution_log) 通过后台守护线程异步写入，避免每次路由请求
    同步写库带来的延迟；DB 不可用时仍正常返回路由结果 (best-effort)。
    """

    def __init__(self) -> None:
        # 进化日志异步写入队列 + 后台守护线程消费者
        self._log_queue: "queue.Queue" = queue.Queue()
        self._log_thread = threading.Thread(target=self._log_worker, daemon=True)
        self._log_thread.start()

    def route_intent(
        self,
        intent: str,
        user_id: str = "system",
        project_id: str = "",
        trace_id: str = "",
    ) -> Dict[str, object]:
        """路由意图，返回 {workflow_id, priority, persona_config(JSON str)}。"""
        layer, complexity, workflow_id = classify_intent(intent)
        priority = self._priority(layer, complexity, user_id)
        persona = self._persona(layer, complexity, user_id, project_id)

        self._log(layer, "route", {
            "intent": intent,
            "workflow_id": workflow_id,
            "priority": priority,
            "complexity": complexity,
            "user_id": user_id,
            "project_id": project_id,
            "trace_id": trace_id,
        })

        return {
            "layer": layer,
            "complexity": complexity,
            "workflow_id": workflow_id,
            "priority": priority,
            "persona_config": json.dumps(persona, ensure_ascii=False),
        }

    def query_priority(self, task_id: str) -> int:
        """查询任务优先级。无历史时按任务指纹长度给一个合理默认。"""
        if not task_id:
            return LAYER_BASE_PRIORITY["L1"]
        # best-effort 查库
        try:
            from core.database import session_scope
            from sqlmodel import select
            from core.database.models import TaskFingerprint

            with session_scope() as s:
                fp = s.exec(
                    select(TaskFingerprint).where(
                        TaskFingerprint.fingerprint_hash == task_id
                    )
                ).first()
                if fp is not None:
                    return LAYER_BASE_PRIORITY["L3"] + min(1, fp.hit_count // 5)
        except Exception as e:  # pragma: no cover - DB 可选
            logger.debug("query_priority DB 查询失败，走默认: %s", e)
        # 默认: 基于 task_id 稳定派生
        return 4 + (len(task_id) % 5)

    def inject_persona(self, user_id: str, project_id: str) -> str:
        """注入人设配置 (成本-精度策略)。优先读取 AgentCARD，否则给默认。"""
        layer = "L2"
        try:
            from core.database import session_scope
            from sqlmodel import select
            from core.database.models import AgentCard

            with session_scope() as s:
                card = s.exec(
                    select(AgentCard).where(AgentCard.agent_id == (user_id or "hermes"))
                ).first()
                if card is not None and card.strategy_json and card.strategy_json != "{}":
                    return card.strategy_json
        except Exception as e:  # pragma: no cover - DB 可选
            logger.debug("inject_persona DB 查询失败，走默认: %s", e)

        persona = {
            "style": "concise",
            "layer": layer,
            "cost_precision": {
                "draft_model": DRAFT_MODELS[layer],
                "final_model": FINAL_MODELS[layer],
            },
            "extensions": {},
        }
        return json.dumps(persona, ensure_ascii=False)

    # ---- 内部 ----

    def propose_self_modification(
        self, intent: str, meta_decision: Optional[Dict[str, object]] = None,
        proposer: str = "meta_orchestrator",
    ) -> Dict[str, object]:
        """捕获 L3.5 自修改/进化意图，生成受人工门控的提案。

        只落库提案 (status=proposed)，绝不自动改代码/配置 —— 对齐蓝图 HUMANGATE。
        返回提案 dict (含 id)，DB 不可用时仍返回结构化结果 (不阻断服务)。
        """
        target = "system"
        diff: Dict[str, object] = {}
        proposal_id: Optional[int] = None
        try:
            from core.database import session_scope
            from core.database.models import SelfModificationProposal

            with session_scope() as s:
                obj = SelfModificationProposal(
                    proposer_agent_id=proposer,
                    target=target,
                    rationale=intent,
                    diff_json=json.dumps(diff, ensure_ascii=False),
                    status="proposed",
                )
                s.add(obj)
                s.commit()
                proposal_id = obj.id
        except Exception as e:  # pragma: no cover - DB 可选，绝不阻断
            logger.debug("self_modification_proposal 写入失败 (忽略): %s", e)

        return {
            "proposal_id": proposal_id,
            "proposer": proposer,
            "target": target,
            "rationale": intent,
            "diff": diff,
            "status": "proposed",
            "requires_human_approval": True,
        }

    def _priority(self, layer: str, complexity: int, user_id: str) -> int:
        base = LAYER_BASE_PRIORITY.get(layer, 3)
        # 复杂度在层基础上微调 (±2)
        return max(1, min(10, base + (complexity - 5) // 2))

    def _persona(self, layer: str, complexity: int, user_id: str, project_id: str) -> Dict[str, object]:
        return {
            "style": "concise" if complexity <= 5 else "thorough",
            "layer": layer,
            "workflow": WORKFLOWS[layer],
            "cost_precision": {
                "draft_model": DRAFT_MODELS[layer],
                "final_model": FINAL_MODELS[layer],
                "use_draft_for_initial": layer in ("L1", "L2"),
            },
            "extensions": {},
            "project_id": project_id or "",
        }

    def _log(self, layer: str, event_type: str, payload: Dict[str, object]) -> None:
        """非阻塞: 入队，由后台守护线程落库 (best-effort)。"""
        try:
            self._log_queue.put({
                "agent_id": "meta_orchestrator",
                "layer": layer,
                "event_type": event_type,
                "payload": payload or {},
            }, block=False)
        except Exception as e:  # pragma: no cover - 队列异常绝不阻断路由
            logger.warning("日志入队失败(忽略): %s", e)

    def _log_worker(self) -> None:
        """后台守护线程: 消费日志队列并写入 evolution_log。"""
        while True:
            item = self._log_queue.get()
            if item is None:  # 毒丸，退出
                self._log_queue.task_done()
                break
            try:
                self._write_log(item)
            except Exception as e:  # pragma: no cover - best-effort
                logger.debug("evolution_log 异步写入失败(忽略): %s", e)
            finally:
                self._log_queue.task_done()

    def _write_log(self, item: Dict[str, object]) -> None:
        from core.database import session_scope
        from core.database.models import EvolutionLog

        with session_scope() as s:
            s.add(EvolutionLog(
                agent_id=item["agent_id"],
                layer=item["layer"],
                event_type=item["event_type"],
                payload_json=json.dumps(item["payload"], ensure_ascii=False),
            ))
            s.commit()

    def flush(self, timeout: float = 2.0) -> None:
        """等待所有待写入的 evolution_log 落库 (测试/关闭时调用)。"""
        try:
            self._log_queue.join()
        except Exception as e:
            logger.warning("evolution_log flush 超时或异常: %s", e)
