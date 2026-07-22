"""审计日志 — AOS 合规基础设施之一。

负责把 agent 行为事件落盘到 data/audit/audit.jsonl,支持 query 与 get_stats。
源码重建(2026-07-19):原 .py 丢失(仅 .pyc 残留),按调用点契约
(web/app.py + main.py + brain.py) 重建。重建原则:零外部依赖、落盘 jsonl、
线程安全、API 与原版兼容(log/query/get_stats + AuditEvent 枚举)。
"""
from __future__ import annotations

import json
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class AuditEvent(Enum):
    """审计事件类型 — 与 web/app.py + brain.py 调用点保持一致。"""

    AGENT_TOOL_CALL = "agent.tool_call"
    MODEL_REQUEST = "model.request"
    MODEL_RESPONSE = "model.response"
    SYSTEM_ERROR = "system.error"
    DATA_WRITE = "data.write"
    DATA_READ = "data.read"
    SUBAGENT_INVOKE = "subagent.invoke"
    SUBAGENT_RESULT = "subagent.result"
    SUBAGENT_ERROR = "subagent.error"
    SYSTEM_STARTUP = "system.startup"
    SYSTEM_SHUTDOWN = "system.shutdown"
    CONFIG_CHANGE = "system.config_change"


# 默认审计日志路径: data/audit/audit.jsonl
_DEFAULT_AUDIT_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "audit" / "audit.jsonl"
)


class AuditLogger:
    """线程安全的 jsonl 审计日志器。

    每条事件一行 JSON:{ts, event, agent_id, details}。query/get_stats 读同一文件。
    """

    def __init__(self, path: Optional[str] = None):
        self._path = path or os.environ.get("AOS_AUDIT_PATH", _DEFAULT_AUDIT_PATH)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def log(
        self,
        event: Any,
        agent_id: Optional[str] = None,
        details: Optional[dict] = None,
        **kwargs: Any,
    ) -> None:
        """记录审计事件。event 可为 AuditEvent 枚举或字符串。"""
        event_value = event.value if isinstance(event, AuditEvent) else str(event)
        # kwargs 中可能含 agent_id/details 之外的字段,合并到 details
        merged = dict(details or {})
        merged.update(kwargs)
        entry = {
            "ts": time.time(),
            "event": event_value,
            "agent_id": agent_id,
            "details": merged,
        }
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def query(
        self, event_type: Optional[str] = None, limit: int = 100
    ) -> list[dict]:
        """查询审计事件。event_type=None 返回全部;按时间倒序取最近 limit 条。"""
        if not os.path.exists(self._path):
            return []
        results: list[dict] = []
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if event_type and entry.get("event") != event_type:
                        continue
                    results.append(entry)
        # 倒序最近 limit 条
        return list(reversed(results[-limit:]))

    def get_stats(self) -> dict:
        """统计:总数 + 各事件类型计数。"""
        if not os.path.exists(self._path):
            return {"count": 0, "by_event": {}}
        counts: dict[str, int] = {}
        total = 0
        with self._lock:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    event = entry.get("event", "unknown")
                    counts[event] = counts.get(event, 0) + 1
                    total += 1
        return {"count": total, "by_event": counts}

    def flush(self) -> None:
        """刷新日志缓存（当前实现为NO-OP，保持接口兼容）"""
        pass


# 全局单例(线程安全懒加载)
_logger_instance: Optional[AuditLogger] = None
_logger_lock = threading.Lock()


def get_audit_logger() -> AuditLogger:
    """获取全局 AuditLogger 单例。"""
    global _logger_instance
    if _logger_instance is None:
        with _logger_lock:
            if _logger_instance is None:
                _logger_instance = AuditLogger()
    return _logger_instance
