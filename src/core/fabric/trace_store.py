"""任务级白盒 trace 生产者（理念8「白盒才可进化」的落地一环）。

AOS 已有 MemoryDistiller 常驻循环，能把 `_traces/` 下的 `route_outcomes.jsonl`
与 `trace_*.json` 提炼成 `distilled_memory.jsonl`（失败模式 / 能力可靠性 /
延迟事实）。但此前**没有任何生产者写 `trace_*.json`**——蒸馏器只吃到路由层
的 route_outcomes，吃不到「任务级每步 trace」。

本模块补上这个生产者：
- 编排芯粒 / 内容导演 每跑一个 task，用 TaskTraceStore 累积「每步路由结果」，
  任务结束 flush 成 `_traces/trace_<id>.json`。
- schema 严格对齐 MemoryDistiller._distill_trace_file 的期望：
    { "task_id", "input": {"task"}, "steps": [{capability, engine, ok, error, latency_ms}],
      "metrics": {"latency_ms"}, "ts", "ok" }
  让蒸馏器能把任务级 trace 提炼成 failure_pattern / capability_reliability / latency_fact。
- 纯 stdlib、best-effort、绝不抛异常（失败只记日志），不拖垮主流程。

TracedRoute 是零侵入包裹：把任意 route_fn(capability, payload) 包一层，
自动把每步成功/失败/延迟累加进 TaskTraceStore，调用方无感。
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _traces_dir() -> Path:
    """默认落盘目录：与 RouteOutcomeStore 一致（src/_traces）。"""
    here = os.path.abspath(__file__)
    src_dir = os.path.dirname(os.path.dirname(here))      # .../src
    return Path(src_dir) / "_traces"


class TaskTraceStore:
    """一个 task 的逐步 trace 累加器，finish 时 flush 成 trace_<id>.json。"""

    def __init__(self, traces_dir: Optional[str] = None) -> None:
        self._dir = Path(traces_dir) if traces_dir else _traces_dir()
        self._buf: Dict[str, Dict[str, Any]] = {}

    def begin(self, trace_id: str, goal: str) -> None:
        self._buf[trace_id] = {
            "task_id": trace_id,
            "input": {"task": goal},
            "steps": [],
            "metrics": {},
            "ts": datetime.now(timezone.utc).isoformat(),
            "ok": True,
        }

    def add_step(self, trace_id: str, capability: str,
                 engine: Optional[str] = None, ok: bool = True,
                 error: Optional[str] = None,
                 latency_ms: Optional[float] = None) -> None:
        buf = self._buf.get(trace_id)
        if buf is None:
            return
        rec: Dict[str, Any] = {
            "capability": capability,
            "engine": engine,
            "ok": bool(ok),
        }
        if error is not None:
            rec["error"] = str(error)
        if latency_ms is not None:
            rec["latency_ms"] = latency_ms
        buf["steps"].append(rec)

    def finish(self, trace_id: str, ok: bool = True) -> Optional[str]:
        """flush 成 trace_<id>.json，返回路径；失败返回 None（绝不抛）。"""
        buf = self._buf.pop(trace_id, None)
        if buf is None:
            return None
        buf["ok"] = bool(ok)
        total_ms = 0.0
        for s in buf["steps"]:
            lm = s.get("latency_ms")
            if isinstance(lm, (int, float)):
                total_ms += lm
        if buf["steps"]:
            buf["metrics"]["latency_ms"] = round(total_ms, 2)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            path = self._dir / f"trace_{trace_id}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(buf, f, ensure_ascii=False, indent=2)
            return str(path)
        except Exception as e:  # noqa: BLE001 - 落盘失败不致命
            logger.warning("trace flush failed %s: %s", trace_id, e)
            return None


class TracedRoute:
    """零侵入包裹 route_fn：自动把每步结果累加进 TaskTraceStore。

    用法：
        traced = TracedRoute(self._route_fn, store, task_id)
        self._route_fn = traced   # 之后所有内部调用自动埋点
    route_fn 返回 InvokeResult 或裸 dict 都兼容（蒸馏器只关心 steps）。
    """

    def __init__(self, route_fn, store: "TaskTraceStore", trace_id: str) -> None:
        self._fn = route_fn
        self._store = store
        self._tid = trace_id

    def __call__(self, capability: str, payload: Dict[str, Any]):
        from core.fabric.adapter import InvokeResult
        t0 = time.perf_counter()
        try:
            res = self._fn(capability, payload)
        except Exception as e:  # noqa: BLE001 - 异常也要记一笔失败 trace
            dt = (time.perf_counter() - t0) * 1000.0
            self._store.add_step(self._tid, capability, None, False, repr(e), dt)
            raise
        dt = (time.perf_counter() - t0) * 1000.0
        eng = res.engine_id if isinstance(res, InvokeResult) else None
        ok = bool(getattr(res, "ok", True)) if isinstance(res, InvokeResult) else True
        err = getattr(res, "error", None) if isinstance(res, InvokeResult) else None
        self._store.add_step(self._tid, capability, eng, ok, err, dt)
        return res
