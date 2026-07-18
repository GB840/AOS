"""调用追踪 — AOS 合规基础设施之一。

记录请求级 trace 链路(simple span 数据)。源码重建(2026-07-19):
原 .py 丢失(仅 .pyc 残留),按 brain.py + main.py 调用点契约重建。
API:start_trace / add_span / finish_trace / list_traces / get_trace / get_stats。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Optional


_DEFAULT_TRACE_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "trace" / "traces.jsonl"
)


class Tracer:
    """简单的 jsonl 调用追踪器。"""

    def __init__(self, path: Optional[str] = None):
        self._path = path or os.environ.get("AOS_TRACE_PATH", _DEFAULT_TRACE_PATH)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)

    def start_trace(
        self, name: str, parent_trace_id: Optional[str] = None, **tags: Any
    ) -> str:
        """开启一个 trace,返回 trace_id。"""
        trace_id = parent_trace_id or f"tr-{secrets.token_hex(8)}"
        entry = {
            "ts": time.time(),
            "trace_id": trace_id,
            "type": "trace_start",
            "name": name,
            "tags": tags,
        }
        self._append(entry)
        return trace_id

    def add_span(
        self,
        trace_id: str,
        span_name: str,
        duration_ms: Optional[float] = None,
        **fields: Any,
    ) -> None:
        """往现有 trace 添加 span。"""
        entry = {
            "ts": time.time(),
            "trace_id": trace_id,
            "type": "span",
            "name": span_name,
            "duration_ms": duration_ms,
            **fields,
        }
        self._append(entry)

    def finish_trace(
        self, trace_id: str, status: str = "ok", **fields: Any
    ) -> None:
        entry = {
            "ts": time.time(),
            "trace_id": trace_id,
            "type": "trace_finish",
            "status": status,
            **fields,
        }
        self._append(entry)

    def _append(self, entry: dict) -> None:
        with self._lock:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def list_traces(self, limit: int = 100) -> list[dict]:
        """列出最近的 N 个 trace(按 trace_id 分组,取最近 limit 个)。"""
        if not os.path.exists(self._path):
            return []
        traces: dict[str, dict] = {}
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
                    tid = entry.get("trace_id")
                    if not tid:
                        continue
                    traces.setdefault(tid, {"trace_id": tid, "events": []})
                    traces[tid]["events"].append(entry)
        # 取最近 limit 个(按最后一个事件 ts 排序)
        sorted_traces = sorted(
            traces.values(),
            key=lambda t: t["events"][-1].get("ts", 0),
            reverse=True,
        )
        return sorted_traces[:limit]

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """获取指定 trace 的完整事件流。"""
        if not os.path.exists(self._path):
            return None
        events: list[dict] = []
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
                    if entry.get("trace_id") == trace_id:
                        events.append(entry)
        if not events:
            return None
        return {"trace_id": trace_id, "events": events}

    def get_stats(self) -> dict:
        """统计:trace 总数、span 总数、最近活跃数。"""
        if not os.path.exists(self._path):
            return {"traces": 0, "spans": 0, "active": 0}
        trace_ids: set[str] = set()
        spans = 0
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
                    tid = entry.get("trace_id")
                    if tid:
                        trace_ids.add(tid)
                    if entry.get("type") == "span":
                        spans += 1
        return {"traces": len(trace_ids), "spans": spans, "active": len(trace_ids)}


_tracer_instance: Optional[Tracer] = None
_tracer_lock = threading.Lock()


def get_tracer() -> Tracer:
    """获取全局 Tracer 单例。"""
    global _tracer_instance
    if _tracer_instance is None:
        with _tracer_lock:
            if _tracer_instance is None:
                _tracer_instance = Tracer()
    return _tracer_instance
