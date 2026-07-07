"""
AOS v5.0 — 事件溯源 (EventStore)

对标蓝图 EVENT_STORE(事件存储 + 快照)。满足蓝图节点: EVENT_STORE + STP 的快照部分。
设计原则 (严谨 + 开放 + 灵活):
  - 追加写: append() 保证同一聚合内 seq 单调递增 (DB 层用 max+1 计算)。
  - 回放: replay() 按 seq 顺序返回事件, 支持从某版本起 (配合快照)。
  - 快照: save_snapshot/load_latest_snapshot 加速回放。
  - 优雅降级: DB 不可用时退化为内存实现, 不阻断服务 (best-effort)。
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventStore:
    """追加式事件存储。默认走 ORM; 失败时退内存。"""

    def __init__(self):
        self._mem: Dict[str, List[Dict[str, Any]]] = {}
        self._mem_snaps: Dict[str, Dict[str, Any]] = {}

    def _agg_key(self, aggregate_type: str, aggregate_id: str) -> str:
        return f"{aggregate_type}:{aggregate_id}"

    def append(self, aggregate_type: str, aggregate_id: str, event_type: str,
               payload: Dict[str, Any]) -> int:
        """追加一个事件, 返回其 seq。"""
        try:
            from core.database import session_scope
            from core.database.models import EventStore as EventStoreRow
            from sqlmodel import func, select

            with session_scope() as s:
                cur = s.exec(
                    select(func.coalesce(func.max(EventStoreRow.seq), 0)).where(
                        EventStoreRow.aggregate_type == aggregate_type,
                        EventStoreRow.aggregate_id == aggregate_id,
                    )
                ).first()
                seq = (cur or 0) + 1
                s.add(EventStoreRow(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    seq=seq,
                    event_type=event_type,
                    payload_json=json.dumps(payload, ensure_ascii=False),
                ))
                s.commit()
                return seq
        except Exception as e:  # pragma: no cover - DB 不可用时内存降级
            logger.debug("event_store 落库失败, 内存降级: %s", e)
            key = self._agg_key(aggregate_type, aggregate_id)
            seq = len(self._mem.get(key, [])) + 1
            self._mem.setdefault(key, []).append({
                "seq": seq, "event_type": event_type, "payload": payload,
            })
            return seq

    def replay(self, aggregate_type: str, aggregate_id: str,
               from_seq: int = 0) -> List[Dict[str, Any]]:
        """按 seq 顺序回放事件。"""
        try:
            from core.database import session_scope
            from core.database.models import EventStore as EventStoreRow
            from sqlmodel import select

            with session_scope() as s:
                rows = s.exec(
                    select(EventStoreRow)
                    .where(EventStoreRow.aggregate_type == aggregate_type,
                           EventStoreRow.aggregate_id == aggregate_id,
                           EventStoreRow.seq > from_seq)
                    .order_by(EventStoreRow.seq)
                ).all()
                return [
                    {"seq": r.seq, "event_type": r.event_type,
                     "payload": json.loads(r.payload_json)}
                    for r in rows
                ]
        except Exception as e:  # pragma: no cover - 内存降级
            logger.debug("event_store 读取失败, 内存回放: %s", e)
            key = self._agg_key(aggregate_type, aggregate_id)
            return [ev for ev in self._mem.get(key, []) if ev["seq"] > from_seq]

    def save_snapshot(self, aggregate_type: str, aggregate_id: str, version: int,
                      state: Dict[str, Any]) -> None:
        try:
            from core.database import session_scope
            from core.database.models import Snapshot
            from sqlmodel import select

            with session_scope() as s:
                existing = s.exec(
                    select(Snapshot).where(
                        Snapshot.aggregate_type == aggregate_type,
                        Snapshot.aggregate_id == aggregate_id,
                    )
                ).first()
                if existing:
                    existing.version = version
                    existing.state_json = json.dumps(state, ensure_ascii=False)
                else:
                    s.add(Snapshot(
                        aggregate_type=aggregate_type,
                        aggregate_id=aggregate_id,
                        version=version,
                        state_json=json.dumps(state, ensure_ascii=False),
                    ))
                s.commit()
        except Exception as e:  # pragma: no cover
            logger.debug("snapshot 落库失败, 内存降级: %s", e)
            key = self._agg_key(aggregate_type, aggregate_id)
            self._mem_snaps[key] = {"version": version, "state": state}

    def load_latest_snapshot(self, aggregate_type: str, aggregate_id: str
                             ) -> Optional[Dict[str, Any]]:
        try:
            from core.database import session_scope
            from core.database.models import Snapshot
            from sqlmodel import select

            with session_scope() as s:
                row = s.exec(
                    select(Snapshot).where(
                        Snapshot.aggregate_type == aggregate_type,
                        Snapshot.aggregate_id == aggregate_id,
                    )
                ).first()
                return {"version": row.version, "state": json.loads(row.state_json)} if row else None
        except Exception as e:  # pragma: no cover
            logger.debug("snapshot 读取失败, 内存降级: %s", e)
            key = self._agg_key(aggregate_type, aggregate_id)
            snap = self._mem_snaps.get(key)
            return snap if snap else None
