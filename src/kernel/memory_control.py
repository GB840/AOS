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


# 理念8「限最大存储条数防磁盘打满」：controllable_memory.jsonl 事件日志硬上限。
# 与 trace_store._MAX_TRACE_FILES=500 / route_outcome_store._MAX_ROUTE_OUTCOMES=2000
# 同源纪律。本文件是 append-only 事件日志（同一 memory_id 的 add/edit/delete/rollback
# 各 append 一条），膨胀主要来自 edit 历史累积。达上限时做语义化 compact：基于内存
# 视图（_mem，每 id 已是最新状态）重写文件，每 id 只留 1 条最新记录——审计信息已
# 嵌入 edit_history（每条含 ts/action/snapshot），故丢弃中间事件不丢审计；deleted
# 记录保留（软删可恢复，数据保全铁律）。
_MAX_CONTROLLABLE = 2000
# 每次 _append 都读全文件行数开销大，用内存计数器每 N 次才检查一次。
# 进程重启计数器归零只会让首次 compact 晚到 N 次后，不影响正确性。
_TRIM_CHECK_EVERY = 50


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
        # 理念8 轮转计数器（_compact 触发节流）
        self._since_last_trim = 0

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
        # 理念8：事件日志防膨胀的节流 compact（调用方已持 self._lock，安全）
        self._since_last_trim += 1
        if self._since_last_trim >= _TRIM_CHECK_EVERY:
            self._since_last_trim = 0
            self._compact()

    def _compact(self) -> None:
        """达 _MAX_CONTROLLABLE 上限时压缩事件日志：每 id 只留最新一条记录。

        _mem 已是「同 id 后者覆盖前者」的最新视图（含完整 edit_history），故直接
        基于 _mem 重写文件即可去重——审计信息（ts/action/snapshot）已嵌入每条
        记录的 edit_history，丢弃中间事件不丢审计；deleted 记录保留（软删可恢复）。
        原子写回（先写 .tmp 再 replace），避免中途崩溃损坏事件日志。
        compact 失败不致命（best-effort，与本模块整体纪律一致）。
        """
        try:
            if not self._path.is_file():
                return
            # 看文件实际行数（_mem 是去重视图，行数远大于 _mem 大小才需 compact）
            with open(self._path, "r", encoding="utf-8") as f:
                count = sum(1 for ln in f if ln.strip())
            if count < _MAX_CONTROLLABLE:
                return
            # 按 updated_at 排序，最新在后（与 append 时间序一致）
            records = sorted(self._mem.values(),
                             key=lambda r: r.get("updated_at", ""))
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            tmp.replace(self._path)
        except Exception as e:  # noqa: BLE001 - compact 失败不致命
            import logging
            logging.getLogger(__name__).debug(
                "controllable_memory compact failed: %s", e)

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
