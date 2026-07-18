"""可编辑 / 可回滚的项目级记忆控制面（任务②，补全理念8「白盒才可进化」最后一公里）。

现状（摸排结论）：AOS 记忆是「全局 + 蒸馏后不可干预」的——DistilledMemory 无 id /
scope / project_id，落盘 distilled_memory.jsonl 为 append-only，无 list / get / delete /
edit / rollback 任何端点。本模块在**不改动既有蒸馏流**的前提下，新增一层「可干预记忆库」：

- 后端：src/_traces/controllable_memory.jsonl（append-only 事件日志，每条含 edit_history）
- 每条记忆有稳定 id、scope(global/user/project)、project_id、version、edit_history
- edit：旧值进 edit_history 快照，version+1
- rollback：从快照恢复历史版本
- delete：软删除（可恢复）

设计原则：
- 诚实：只读真实落盘，软删/回滚都留痕（event log），不静默覆盖。
- 零新增外部依赖：纯标准库。
- 与 mem0 双后端分裂无关——本控制面自持 JSONL，避免再引入一套不可控的向量库。
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryControlStore:
    """可编辑/可回滚的项目级记忆库（JSONL 事件日志后端）。"""

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            here = os.path.abspath(__file__)
            kernel_dir = os.path.dirname(here)
            src_dir = os.path.dirname(kernel_dir)
            path = os.path.join(src_dir, "_traces", "controllable_memory.jsonl")
        self._path = Path(path)
        self._lock = threading.Lock()
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._load()

    # ---- 加载（事件日志 → 内存最新视图）----
    def _load(self) -> None:
        self._mem.clear()
        if not self._path.is_file():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    mid = rec.get("id")
                    if mid:
                        self._mem[mid] = rec
        except OSError:
            return

    def _append(self, rec: Dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._mem[rec["id"]] = rec

    # ---- CRUD ----
    def add(self, text: str, category: str, source: str = "manual",
            confidence: float = 0.5, scope: str = "global",
            project_id: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        mid = uuid.uuid4().hex
        now = _now()
        rec = {
            "id": mid,
            "text": text,
            "category": category,
            "source": source,
            "confidence": confidence,
            "scope": scope,
            "project_id": project_id,
            "metadata": metadata or {},
            "version": 1,
            "created_at": now,
            "updated_at": now,
            "edit_history": [],
            "deleted": False,
        }
        with self._lock:
            self._append(rec)
        return rec

    def list(self, scope: Optional[str] = None,
             project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._lock:
            items = [r for r in self._mem.values() if not r.get("deleted")]
        if scope is not None:
            items = [r for r in items if r.get("scope") == scope]
        if project_id is not None:
            items = [r for r in items if r.get("project_id") == project_id]
        return sorted(items, key=lambda r: r.get("updated_at", ""), reverse=True)

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._mem.get(memory_id)

    def update(self, memory_id: str, text: Optional[str] = None,
               category: Optional[str] = None, confidence: Optional[float] = None,
               metadata: Optional[Dict[str, Any]] = None, scope: Optional[str] = None,
               project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._mem.get(memory_id)
            if rec is None or rec.get("deleted"):
                return None
            snapshot = {
                "text": rec.get("text"),
                "category": rec.get("category"),
                "confidence": rec.get("confidence"),
                "scope": rec.get("scope"),
                "project_id": rec.get("project_id"),
                "metadata": rec.get("metadata"),
            }
            rec["edit_history"].append({
                "version": rec["version"],
                "ts": _now(),
                "action": "edit",
                "snapshot": snapshot,
            })
            if text is not None:
                rec["text"] = text
            if category is not None:
                rec["category"] = category
            if confidence is not None:
                rec["confidence"] = confidence
            if metadata is not None:
                rec["metadata"] = metadata
            if scope is not None:
                rec["scope"] = scope
            if project_id is not None:
                rec["project_id"] = project_id
            rec["version"] += 1
            rec["updated_at"] = _now()
            self._append(rec)
            return rec

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            rec = self._mem.get(memory_id)
            if rec is None or rec.get("deleted"):
                return False
            rec["deleted"] = True
            rec["deleted_at"] = _now()
            rec["version"] += 1
            self._append(rec)
            return True

    def rollback(self, memory_id: str, version: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            rec = self._mem.get(memory_id)
            if rec is None or rec.get("deleted"):
                return None
            snap = None
            for h in rec.get("edit_history", []):
                if h.get("version") == version:
                    snap = h.get("snapshot")
                    break
            if snap is None:
                return None
            rec["edit_history"].append({
                "version": rec["version"],
                "ts": _now(),
                "action": "rollback_to",
                "from_version": rec["version"],
                "restored_version": version,
            })
            for k, v in snap.items():
                rec[k] = v
            rec["version"] += 1
            rec["updated_at"] = _now()
            self._append(rec)
            return rec
