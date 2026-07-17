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

    # ── 事件记录 ──

    def record_run(self, workflow_id: str, run_data: Dict[str, Any]) -> None:
        """记录一次运行。"""
        event = {
            "type": "workflow_run",
            "workflow_id": workflow_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            **run_data,
        }
        self._buffer.append(event)
        self._update_agent_metrics(workflow_id, run_data)

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
            **feedback,
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
