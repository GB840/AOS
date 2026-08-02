"""宪法治理层 —— CONST3 节点真接开源（constitutional-agent，MIT）。

项目：constitutional-agent（PyPI，MIT，纯 Python 轻量）
官方：https://pypi.org/project/constitutional-agent/

AOS 的 CONST3 原本标「自研等价」（compliance/ + values_market 宪法红线）。
现真接 constitutional-agent 作为本地宪法治理引擎：用其 `Constitution` 做
六闸门评估（SixGateEvaluator）+ 硬约束（HardConstraint），无需外部 LLM 即可
在本地对行为/内容做合规门控，与 AOS 既有 `CONSTITUTION_REDLINES` 红线互补。

设计纪律：重依赖惰性导入；未安装时 `CONSTITUTIONAL_AGENT_AVAILABLE=False`，
health() 返回 False，绝不谎报治理可用。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import constitutional_agent  # 纯 Python 轻量，惰性导入

    CONSTITUTIONAL_AGENT_AVAILABLE = True
except Exception:  # pragma: no cover
    constitutional_agent = None
    CONSTITUTIONAL_AGENT_AVAILABLE = False


class ConstitutionalGovernor:
    """封装 constitutional_agent.Constitution 的本地宪法治理门控。"""

    def __init__(self, config: Optional[dict] = None) -> None:
        self._config = config or {}
        self._constitution = None
        if CONSTITUTIONAL_AGENT_AVAILABLE and config:
            try:
                self._constitution = constitutional_agent.Constitution(config)
            except Exception as e:
                logger.warning("Constitution 构造失败：%s", e)
                self._constitution = None

    @property
    def available(self) -> bool:
        return CONSTITUTIONAL_AGENT_AVAILABLE

    def health_detail(self) -> dict:
        return {
            "engine": "constitutional-agent",
            "license": "MIT",
            "lib_available": CONSTITUTIONAL_AGENT_AVAILABLE,
            "ready": CONSTITUTIONAL_AGENT_AVAILABLE,
            "note": "MIT 本地宪法治理（SixGate + HardConstraint），无需外部 LLM；与 AOS CONSTITUTION_REDLINES 互补",
        }

    def ensure_loaded(self):
        """惰性加载默认宪法（若尚未加载）。"""
        if self._constitution is None and CONSTITUTIONAL_AGENT_AVAILABLE:
            self._constitution = constitutional_agent.Constitution.from_defaults()
        return self._constitution

    def evaluate(self, context: dict) -> dict:
        """对一段行为/内容上下文做宪法评估，返回结构化结果。

        返回字段（来自 ConstitutionResult）：
        - blocking_gates: 阻断闸门列表（任一非空即不放行）
        - hard_constraint_violations: 硬约束违例
        - targets_met: 目标达成情况
        - summary: 文本摘要
        - blocking: 是否任一闸门阻断
        - allowed: 是否合规放行（无阻断且无硬约束违例）
        """
        if not CONSTITUTIONAL_AGENT_AVAILABLE:
            raise RuntimeError("constitutional-agent 未安装：pip install constitutional-agent")
        c = self.ensure_loaded()
        result = c.evaluate(context=context)
        blocking = list(getattr(result, "blocking_gates", []) or [])
        hc_v = list(getattr(result, "hard_constraint_violations", []) or [])
        return {
            "blocking_gates": [str(g) for g in blocking],
            "hard_constraint_violations": [str(v) for v in hc_v],
            "targets_met": getattr(result, "targets_met", None),
            "summary": getattr(result, "summary", None),
            "blocking": bool(blocking),
            "allowed": not blocking and not hc_v,
            "evaluation_count": getattr(c, "evaluation_count", None),
        }

    def is_allowed(self, context: dict) -> bool:
        """便捷门控：合规放行返回 True，否则 False（门控失败不抛异常）。"""
        try:
            return bool(self.evaluate(context).get("allowed", False))
        except Exception as e:
            logger.warning("宪法评估异常，默认不放行：%s", e)
            return False
