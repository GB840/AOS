"""Pulse —— 使用数据采集与分析。

采集智能体/工作流的使用数据，提供分析和洞察。

设计原则：
- 非侵入：不影响主流程，异步记录
- 真实数据：所有指标都从真实运行中来，不伪造
- 可观测：成功率、耗时、失败原因、热门步骤，一目了然
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _pulse_dir() -> str:
    pulse_dir = os.environ.get(
        "AOS_PULSE_DIR",
        os.path.join("data", "workspaces", "fabric", "pulse"),
    )
    os.makedirs(pulse_dir, exist_ok=True)
    return pulse_dir


def _metrics_path() -> str:
    return os.path.join(_pulse_dir(), "metrics.json")


def _events_path() -> str:
    return os.path.join(_pulse_dir(), "events.jsonl")


class PulseCollector:
    """数据采集器。"""

    def __init__(self):
        self._metrics = self._load_metrics()
        self._buffer: List[Dict] = []
        self._max_buffer = 100
        self._cost_tracker = None  # 懒加载，避免循环 import

    def _get_cost_tracker(self):
        """懒加载 CostTracker（避免循环 import）。"""
        if self._cost_tracker is not None:
            return self._cost_tracker
        try:
            from kernel.pulse.cost_tracker import get_cost_tracker
            self._cost_tracker = get_cost_tracker()
        except Exception as e:  # noqa: BLE001
            logger.debug("CostTracker 不可用: %s", e)
            self._cost_tracker = False  # 标记不可用
        return self._cost_tracker if self._cost_tracker is not False else None

    # ── 事件记录 ──

    def record_run(self, workflow_id: str, run_data: Dict[str, Any]) -> None:
        """记录一次运行。

        如果 run_data 包含 token_usage 字段（dict），会自动转记到 CostTracker。
        token_usage 字段格式：
            {model, prompt_tokens, completion_tokens, user_id, agent_id, run_id, duration_ms}
        """
        event = {
            "type": "workflow_run",
            "workflow_id": workflow_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **run_data,
        }
        self._buffer.append(event)
        self._update_agent_metrics(workflow_id, run_data)

        # Token 用量进 CostTracker
        tu = run_data.get("token_usage")
        if isinstance(tu, dict):
            try:
                tracker = self._get_cost_tracker()
                if tracker is not None:
                    tracker.record(
                        workflow_id=workflow_id,
                        user_id=tu.get("user_id", "anonymous"),
                        agent_id=tu.get("agent_id", ""),
                        model=tu.get("model", ""),
                        prompt_tokens=int(tu.get("prompt_tokens", 0)),
                        completion_tokens=int(tu.get("completion_tokens", 0)),
                        duration_ms=float(tu.get("duration_ms", 0)),
                        run_id=tu.get("run_id", run_data.get("run_id", "")),
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug("Token 用量记录失败: %s", e)

        if len(self._buffer) >= self._max_buffer:
            self._flush()

    def record_step(self, workflow_id: str, step_data: Dict[str, Any]) -> None:
        """记录单步执行。"""
        event = {
            "type": "step_run",
            "workflow_id": workflow_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **step_data,
        }
        self._buffer.append(event)

        if len(self._buffer) >= self._max_buffer:
            self._flush()

    def record_feedback(self, workflow_id: str, feedback: Dict[str, Any]) -> None:
        """记录用户反馈。"""
        event = {
            "type": "user_feedback",
            "workflow_id": workflow_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "feedback": feedback,  # 嵌套保存，避免覆盖 type 等关键字段
        }
        self._buffer.append(event)
        self._flush()

    # ── 统计查询 ──

    def get_agent_metrics(self, workflow_id: str) -> Dict[str, Any]:
        """获取单个智能体的统计数据。"""
        return self._metrics.get(workflow_id, {
            "total_runs": 0,
            "success_runs": 0,
            "failed_runs": 0,
            "success_rate": 0.0,
            "avg_duration": 0.0,
            "total_duration": 0.0,
            "step_stats": {},
            "last_run": "",
        })

    def get_all_metrics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取所有智能体的统计（按使用量排序）。"""
        items = []
        for wf_id, m in self._metrics.items():
            items.append({"workflow_id": wf_id, **m})
        items.sort(key=lambda x: x.get("total_runs", 0), reverse=True)
        return items[:limit]

    def get_failure_analysis(self, workflow_id: str) -> Dict[str, Any]:
        """失败分析：哪些步骤最容易失败，原因是什么。"""
        # 从事件历史中分析
        step_failures = defaultdict(int)
        failure_reasons = defaultdict(int)

        for event in self._buffer:
            if event.get("type") == "step_run" and event.get("workflow_id") == workflow_id:
                if not event.get("ok", True):
                    step = event.get("step_name", "unknown")
                    step_failures[step] += 1
                    reason = event.get("error", "unknown")[:50]
                    failure_reasons[reason] += 1

        return {
            "step_failures": dict(sorted(step_failures.items(), key=lambda x: x[1], reverse=True)),
            "failure_reasons": dict(sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:10]),
        }

    def get_feedbacks(self, *, feedback_type: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        """获取反馈数据（含用户反馈、内容反馈等）。

        从事件文件中读取所有 user_feedback 类型的事件，可选按类型过滤。

        Args:
            feedback_type: 反馈类型过滤（如 "content_feedback"），为空返回所有
            limit: 最多返回条数

        Returns:
            反馈事件列表，按时间倒序
        """
        feedbacks = []
        events_path = _events_path()

        # 先读 buffer 里的（还没 flush 的）
        for event in reversed(self._buffer):
            if event.get("type") == "user_feedback":
                fb = event.get("feedback", {})
                if not feedback_type or fb.get("type") == feedback_type:
                    feedbacks.append(event)
                    if len(feedbacks) >= limit:
                        return feedbacks

        # 再读文件里的
        if os.path.exists(events_path):
            try:
                with open(events_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        if event.get("type") == "user_feedback":
                            fb = event.get("feedback", {})
                            if not feedback_type or fb.get("type") == feedback_type:
                                feedbacks.append(event)
                                if len(feedbacks) >= limit:
                                    break
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                logger.debug("读取反馈事件失败: %s", e)

        return feedbacks[:limit]

    # ── 成本可观测（Task 1: Cost Observability）──

    def get_cost_breakdown(self, *, workflow_id: str = "", user_id: str = "",
                           agent_id: str = "", since: str = "",
                           until: str = "", limit: int = 10000) -> Dict[str, Any]:
        """获取成本聚合（按 model/workflow/user/agent 维度）。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return {"ok": False, "error": "CostTracker 不可用"}
        bd = tracker.get_breakdown(
            workflow_id=workflow_id, user_id=user_id,
            agent_id=agent_id, since=since, until=until, limit=limit,
        )
        return {
            "ok": True,
            "total_cost": bd.total_cost,
            "total_tokens": bd.total_tokens,
            "total_prompt_tokens": bd.total_prompt_tokens,
            "total_completion_tokens": bd.total_completion_tokens,
            "record_count": bd.record_count,
            "by_model": bd.by_model,
            "by_workflow": bd.by_workflow,
            "by_user": bd.by_user,
            "by_agent": bd.by_agent,
        }

    def get_cost_records(self, limit: int = 50,
                         workflow_id: str = "") -> List[Dict[str, Any]]:
        """获取最近 N 条成本事件。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return []
        return tracker.get_recent_records(limit=limit, workflow_id=workflow_id)

    def add_cost_alert(self, name: str, scope: str, scope_id: str,
                       period: str, threshold_usd: float) -> Dict[str, Any]:
        """添加一个成本告警。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return {"ok": False, "error": "CostTracker 不可用"}
        from kernel.pulse.cost_tracker import CostAlert
        alert = CostAlert(
            name=name, scope=scope, scope_id=scope_id,
            period=period, threshold_usd=threshold_usd,
        )
        tracker.add_alert(alert)
        return {"ok": True, "alert_id": alert.id}

    def list_cost_alerts(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """列出所有成本告警。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return []
        from dataclasses import asdict
        return [asdict(a) for a in tracker.list_alerts(enabled_only=enabled_only)]

    def delete_cost_alert(self, alert_id: str) -> bool:
        """删除一个成本告警。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return False
        return tracker.delete_alert(alert_id)

    def check_cost_alerts(self) -> List[Dict[str, Any]]:
        """主动检查所有成本告警。"""
        tracker = self._get_cost_tracker()
        if tracker is None:
            return []
        return tracker.check_alerts()

    # ── 内部方法 ──

    def _update_agent_metrics(self, workflow_id: str, run_data: Dict) -> None:
        m = self._metrics.get(workflow_id, {
            "total_runs": 0,
            "success_runs": 0,
            "failed_runs": 0,
            "success_rate": 0.0,
            "avg_duration": 0.0,
            "total_duration": 0.0,
            "step_stats": {},
            "last_run": "",
            "total_tokens": 0,
            "total_cost_usd": 0.0,
        })

        m["total_runs"] += 1
        status = run_data.get("status", "success")
        if status == "success":
            m["success_runs"] += 1
        else:
            m["failed_runs"] += 1

        total = m["total_runs"]
        m["success_rate"] = round(m["success_runs"] / total * 100, 1) if total > 0 else 0

        duration = run_data.get("duration", 0)
        m["total_duration"] += duration
        m["avg_duration"] = round(m["total_duration"] / total, 2) if total > 0 else 0
        m["last_run"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        # Token 成本累计
        tu = run_data.get("token_usage")
        if isinstance(tu, dict):
            m["total_tokens"] = m.get("total_tokens", 0) + \
                int(tu.get("prompt_tokens", 0)) + int(tu.get("completion_tokens", 0))
            cost = 0.0
            try:
                from kernel.pulse.cost_tracker import estimate_cost
                cost = estimate_cost(
                    int(tu.get("prompt_tokens", 0)),
                    int(tu.get("completion_tokens", 0)),
                    tu.get("model", ""),
                )
            except Exception:  # noqa: BLE001
                pass
            m["total_cost_usd"] = round(m.get("total_cost_usd", 0.0) + cost, 6)

        self._metrics[workflow_id] = m
        self._save_metrics()

    def _load_metrics(self) -> Dict[str, Any]:
        if os.path.exists(_metrics_path()):
            try:
                with open(_metrics_path(), "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_metrics(self) -> None:
        try:
            with open(_metrics_path(), "w", encoding="utf-8") as f:
                json.dump(self._metrics, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("保存指标失败: %s", e)

    def _flush(self) -> None:
        """把缓冲的事件写入磁盘。"""
        if not self._buffer:
            return
        try:
            with open(_events_path(), "a", encoding="utf-8") as f:
                for event in self._buffer:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._buffer.clear()
        except Exception as e:
            logger.debug("写入事件失败: %s", e)


# 单例
_collector: Optional[PulseCollector] = None


def get_pulse_collector() -> PulseCollector:
    global _collector
    if _collector is None:
        _collector = PulseCollector()
    return _collector
