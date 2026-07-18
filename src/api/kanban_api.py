"""编排运行可视化看板 API（任务①）。

数据源：OrchestrationChiplet 落盘的 `src/_traces/trace_<id>.json`（理念8「白盒才可进化」
的逐步 trace）。把每个 run 归一化成看板卡片，按运行结果分到泳道列。

设计原则：
- 只读真实落盘数据，无数据则返空列表（绝不伪造运行记录，对齐理念6「诚实」）。
- 纯标准库 + glob，best-effort、不抛异常。
- 不写新持久化，复用已有 trace 落盘契约。
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException


def _traces_dir() -> Path:
    """与 TaskTraceStore 一致的 src/_traces 目录。"""
    here = os.path.abspath(__file__)
    api_dir = os.path.dirname(here)
    src_dir = os.path.dirname(api_dir)
    return Path(src_dir) / "_traces"


def _status_of(rec: Dict[str, Any]) -> str:
    steps = rec.get("steps", []) or []
    if not steps:
        return "empty"
    ok_steps = sum(1 for s in steps if s.get("ok"))
    if ok_steps == len(steps):
        return "success"
    if ok_steps == 0:
        return "failed"
    return "partial"


def _normalize(rec: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    steps = rec.get("steps", []) or []
    ok_steps = sum(1 for s in steps if s.get("ok"))
    total_lat = 0.0
    for s in steps:
        lm = s.get("latency_ms")
        if isinstance(lm, (int, float)):
            total_lat += lm
    return {
        "run_id": run_id,
        "goal": (rec.get("input") or {}).get("task") or "",
        "ok": bool(rec.get("ok", False)),
        "status": _status_of(rec),
        "step_count": len(steps),
        "ok_steps": ok_steps,
        "failed_steps": len(steps) - ok_steps,
        "total_latency_ms": round(total_lat, 2),
        "ts": rec.get("ts") or "",
        "steps": [
            {
                "capability": s.get("capability"),
                "engine": s.get("engine"),
                "ok": bool(s.get("ok")),
                "error": s.get("error"),
                "latency_ms": s.get("latency_ms"),
            }
            for s in steps
        ],
    }


def _load_all() -> List[Dict[str, Any]]:
    d = _traces_dir()
    out: List[Dict[str, Any]] = []
    if not d.is_dir():
        return out
    for p in sorted(glob.glob(str(d / "trace_*.json")), reverse=True):
        try:
            with open(p, "r", encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        run_id = Path(p).stem.replace("trace_", "")
        out.append(_normalize(rec, run_id))
    return out


def mount_kanban_api(app: FastAPI) -> None:
    @app.get("/api/kanban/runs")
    async def kanban_runs(limit: int = 100):
        """列出所有编排运行（归一化看板卡片），按 ts 倒序。"""
        items = _load_all()
        return {"status": "ok", "total": len(items), "items": items[:limit]}

    @app.get("/api/kanban/runs/{run_id}")
    async def kanban_run(run_id: str):
        """取单个运行的完整 step trace。"""
        d = _traces_dir()
        p = d / f"trace_{run_id}.json"
        if not p.is_file():
            raise HTTPException(status_code=404, detail=f"run 不存在: {run_id}")
        try:
            with open(p, "r", encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"status": "ok", "run": _normalize(rec, run_id)}
