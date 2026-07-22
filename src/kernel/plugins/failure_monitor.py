"""插件：MAST 式多智能体失败监控 + 端到端可观测探针。

对账表 L7 要求：
> 新增: 多智能体失败监控（MAST 式）: 14 失败模式埋点：规范/错位/校验
> 结论：针对 41–87% 失败率设可观测护栏
> 升级: 可观测三支柱: 补齐端到端探针

基于 UC Berkeley MAST (arXiv:2503.13657) 的 14 类失败模式分类，
在 AOS 内核中埋点监控，集成 Langfuse tracing。

内核零依赖；本文件位于 plugins/。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FailureMode(str, Enum):
    """MAST 14 类多智能体失败模式（UC Berkeley, arXiv:2503.13657）。"""

    # 规范层 (Specification)
    SPEC_MISMATCH = "spec_mismatch"           # 规范不匹配：Agent 理解偏差
    ROLE_MISALIGNMENT = "role_misalignment"   # 角色错位：Agent 执行了不该做的
    GOAL_DRIFT = "goal_drift"                 # 目标漂移：执行中偏离原始意图

    # 校验层 (Verification)
    VERIFY_FAILURE = "verify_failure"         # 校验失败：Agent 输出未通过验证
    OUTPUT_INVALID = "output_invalid"         # 输出格式无效：JSON/结构化输出错误
    HALLUCINATION = "hallucination"           # 幻觉：编造不存在的信息

    # 执行层 (Execution)
    TOOL_MISUSE = "tool_misuse"               # 工具误用：错误调用工具
    LOOP_DEADLOCK = "loop_deadlock"           # 循环/死锁：Agent 陷入无限循环
    TIMEOUT = "timeout"                       # 超时：执行超过时限
    PERMISSION_DENIED = "permission_denied"   # 权限拒绝：无权限访问资源

    # 基础设施层 (Infrastructure)
    MODEL_UNAVAILABLE = "model_unavailable"   # 模型不可用：LLM API 不可达
    PROTOCOL_ERROR = "protocol_error"         # 协议错误：A2A/MCP 通信异常
    RESOURCE_EXHAUSTED = "resource_exhausted" # 资源耗尽：OOM/磁盘满
    SILENT_FAILURE = "silent_failure"         # 静默失败：无错误但输出为空/无意义


@dataclass
class FailureRecord:
    """单次失败记录。"""

    mode: FailureMode
    agent_id: str = ""
    task_id: str = ""
    message: str = ""
    timestamp: float = field(default_factory=time.time)
    context: Dict[str, Any] = field(default_factory=dict)


class FailureMonitor:
    """MAST 式失败监控器：埋点 + 统计 + Langfuse 集成。

    用法：
        monitor = FailureMonitor()
        monitor.record(FailureMode.TIMEOUT, agent_id="hermes", task_id="t1")
        stats = monitor.get_stats()
        print(stats["failure_rate"])
    """

    # MAST 论文报告的各类失败率基线
    MAST_BASELINE_RATES: Dict[FailureMode, float] = {
        FailureMode.SPEC_MISMATCH: 0.15,
        FailureMode.ROLE_MISALIGNMENT: 0.12,
        FailureMode.GOAL_DRIFT: 0.08,
        FailureMode.VERIFY_FAILURE: 0.10,
        FailureMode.OUTPUT_INVALID: 0.07,
        FailureMode.HALLUCINATION: 0.09,
        FailureMode.TOOL_MISUSE: 0.11,
        FailureMode.LOOP_DEADLOCK: 0.05,
        FailureMode.TIMEOUT: 0.06,
        FailureMode.PERMISSION_DENIED: 0.03,
        FailureMode.MODEL_UNAVAILABLE: 0.04,
        FailureMode.PROTOCOL_ERROR: 0.03,
        FailureMode.RESOURCE_EXHAUSTED: 0.02,
        FailureMode.SILENT_FAILURE: 0.05,
    }

    def __init__(self, max_records: int = 1000) -> None:
        self._lock = threading.RLock()
        self._records: List[FailureRecord] = []
        self._counts: Dict[FailureMode, int] = {m: 0 for m in FailureMode}
        self._total_tasks: int = 0
        self._total_success: int = 0
        self._max_records = max_records
        self._start_time = time.time()

    # ---- 埋点 ----

    def record_task_start(self) -> None:
        with self._lock:
            self._total_tasks += 1

    def record_success(self, agent_id: str = "", task_id: str = "") -> None:
        with self._lock:
            self._total_success += 1

    def record(self, mode: FailureMode, agent_id: str = "",
               task_id: str = "", message: str = "",
               context: Dict[str, Any] = None) -> FailureRecord:
        rec = FailureRecord(
            mode=mode, agent_id=agent_id, task_id=task_id,
            message=message, context=context or {},
        )
        with self._lock:
            self._records.append(rec)
            self._counts[mode] += 1
            if len(self._records) > self._max_records:
                self._records = self._records[-self._max_records:]

        logger.warning("MAST 失败: mode=%s agent=%s task=%s msg=%s",
                       mode.value, agent_id, task_id, message[:80])

        # Langfuse 集成（best-effort）
        self._trace_to_langfuse(rec)

        return rec

    def _trace_to_langfuse(self, rec: FailureRecord) -> None:
        try:
            from core.fabric.adapters.observability_langfuse_adapter import LangfuseAdapter
            adapter = LangfuseAdapter()
            if hasattr(adapter, 'trace'):
                adapter.trace(
                    name=f"failure.{rec.mode.value}",
                    metadata={
                        "failure_mode": rec.mode.value,
                        "agent_id": rec.agent_id,
                        "task_id": rec.task_id,
                        "message": rec.message,
                    },
                )
        except Exception as e:
            logger.warning("FailureMonitor: Langfuse trace failed (non-critical): %s", e)

    # ---- 统计 ----

    def get_stats(self) -> Dict[str, Any]:
        """返回当前失败统计摘要。"""
        with self._lock:
            total = self._total_tasks
            failure_count = total - self._total_success
            return {
                "total_tasks": self._total_tasks,
                "success_count": self._total_success,
                "failure_count": failure_count,
                # 真实任务数；空 monitor（total=0）失败率定义为零，不除零得 1.0
                "failure_rate": round(failure_count / total, 4) if total > 0 else 0.0,
                "uptime_seconds": round(time.time() - self._start_time),
                "counts_by_mode": {m.value: c for m, c in self._counts.items()},
                "top_failures": self._top_failures(5),
                "alerts": self._check_alerts(),
            }

    def _top_failures(self, n: int) -> List[Dict[str, Any]]:
        with self._lock:
            sorted_modes = sorted(self._counts.items(), key=lambda x: -x[1])
            return [
                {
                    "mode": m.value,
                    "count": c,
                    "baseline_rate": self.MAST_BASELINE_RATES.get(m, 0),
                    "actual_rate": round(c / (self._total_tasks or 1), 4),
                }
                for m, c in sorted_modes[:n] if c > 0
            ]

    def _check_alerts(self) -> List[str]:
        """检查是否触发告警阈值（超过 MAST 基线 2 倍）。"""
        with self._lock:
            alerts = []
            total = self._total_tasks or 1
            for mode, baseline in self.MAST_BASELINE_RATES.items():
                actual = self._counts.get(mode, 0) / total
                if actual > baseline * 2 and self._counts.get(mode, 0) >= 3:
                    alerts.append(
                        f"{mode.value}: actual={actual:.1%} > baseline={baseline:.1%} (x2)"
                    )
            return alerts

    # ---- 端到端探针 ----

    def probe_health(self) -> Dict[str, Any]:
        """端到端健康探针：检查各组件状态。"""
        probes = {}
        # 内核网关
        try:
            from kernel.wiring import build_default_kernel
            k = build_default_kernel()
            gw = getattr(k, "_model_gateway", None)
            probes["model_gateway"] = {
                "ok": gw is not None,
                "healthy": gw.health().healthy if gw else False,
                "provider": gw.health().provider if gw else "none",
            }
        except Exception as e:
            probes["model_gateway"] = {"ok": False, "error": str(e)}

        # 技能总线
        try:
            bus = getattr(k, "_skill_bus", None)
            probes["skill_bus"] = {
                "ok": bus is not None,
                "skill_count": len(bus.discover_skills()) if bus else 0,
            }
        except Exception as e:
            probes["skill_bus"] = {"ok": False, "error": str(e)}

        # 失败率
        probes["failure_monitor"] = self.get_stats()

        return probes

    def get_recent_failures(self, n: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return [
                {
                    "mode": r.mode.value,
                    "agent_id": r.agent_id,
                    "task_id": r.task_id,
                    "message": r.message,
                    "timestamp": r.timestamp,
                }
                for r in self._records[-n:]
            ]


# ---- 全局单例 ----
_monitor: Optional[FailureMonitor] = None
_monitor_lock = threading.Lock()


def get_failure_monitor() -> FailureMonitor:
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = FailureMonitor()
    return _monitor


__all__ = ["FailureMode", "FailureRecord", "FailureMonitor", "get_failure_monitor"]