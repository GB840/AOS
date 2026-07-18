"""ContextManager —— 运行时上下文工程（Task 2: Context Engineering）。

落地「上下文窗口即 RAM」理念：
- 监控每步执行后的上下文 token 占用
- 超阈值时按优先级压缩旧步骤（保最新 + 失败 + 关键证据，摘要其余）
- 跨会话持久化关键上下文（断点续跑、长程任务中断恢复）
- 与 CostTracker 复用 count_tokens（零新依赖）

设计原则（Ponytail §10）：
- 复用 cost_tracker.count_tokens，不重造 token 计数
- 标准 JSONL 持久化，便于回放
- 非侵入：调用方传 step_result，ContextManager 自治管理压缩
- 诚实：压缩前/后 token 数、保留/丢弃步骤数都量化呈现

数据落盘路径：data/workspaces/fabric/context/sessions/{session_id}.jsonl
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _context_dir() -> str:
    base = os.environ.get("AOS_CONTEXT_DIR",
                          os.path.join("data", "workspaces", "fabric", "context"))
    os.makedirs(os.path.join(base, "sessions"), exist_ok=True)
    return base


def _session_path(session_id: str) -> str:
    return os.path.join(_context_dir(), "sessions", f"{session_id}.jsonl")


# ── 优先级 ──
PRIORITY_CRITICAL = "critical"  # 必须保留：失败、错误、关键证据
PRIORITY_HIGH = "high"          # 高价值：最近的步骤（最新 N 步）
PRIORITY_NORMAL = "normal"      # 普通：可被压缩
PRIORITY_LOW = "low"            # 低价值：成功且非关键的中间步骤


@dataclass
class ContextEntry:
    """一个上下文条目（对应一个执行步骤或一段对话）。"""
    id: str = ""
    session_id: str = ""
    timestamp: str = ""
    step_index: int = 0
    step_name: str = ""
    capability: str = ""
    content: str = ""  # 文本内容（用于 LLM 上下文）
    output: Dict[str, Any] = field(default_factory=dict)  # 原始输出（结构化）
    ok: bool = True
    error: str = ""
    token_count: int = 0  # 内容的 token 数（自动算）
    priority: str = PRIORITY_NORMAL
    compacted: bool = False  # 是否已被压缩成摘要
    original_id: str = ""  # 如果是被压缩来的，记录原 entry id


class ContextManager:
    """运行时上下文管理器。

    每个 session_id 对应一个独立的上下文窗口（如一次工作流运行、一次 autopilot 任务）。
    所有 entries 维护在内存里，可随时 compact；session 结束时持久化到 JSONL。
    """

    def __init__(self, session_id: str = "",
                 max_tokens: int = 8000,
                 preserve_recent: int = 3,
                 auto_compact: bool = True):
        """初始化一个会话上下文。

        Args:
            session_id: 会话 ID（空则自动生成）
            max_tokens: 上下文 token 上限，超过即触发压缩
            preserve_recent: 压缩时保留最近 N 步不压缩
            auto_compact: 添加 entry 后自动检查是否需要压缩
        """
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.max_tokens = max_tokens
        self.preserve_recent = preserve_recent
        self.auto_compact = auto_compact
        self._entries: List[ContextEntry] = []
        self._lock = threading.Lock()
        self._created_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    # ── 添加 ──

    def add_step(self, step_result: Dict[str, Any]) -> ContextEntry:
        """从一个执行步骤结果添加上下文条目。

        自动计算优先级和 token 数：
        - 失败步骤 → CRITICAL
        - 最近 N 步 → HIGH
        - 成功且非最近 → NORMAL
        """
        from kernel.pulse.cost_tracker import count_tokens

        # 提取文本内容（用于 LLM 上下文）
        content = self._extract_text(step_result)
        token_count = count_tokens(content) if content else 0

        # 自动判定优先级
        ok = step_result.get("ok", True)
        if not ok or step_result.get("error"):
            priority = PRIORITY_CRITICAL
        else:
            priority = PRIORITY_NORMAL  # 添加时先 NORMAL，压缩时再升级 HIGH

        entry = ContextEntry(
            id=uuid.uuid4().hex[:12],
            session_id=self.session_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            step_index=int(step_result.get("step_index", len(self._entries))),
            step_name=step_result.get("step_name", ""),
            capability=step_result.get("capability", ""),
            content=content,
            output=step_result.get("output", {}),
            ok=ok,
            error=step_result.get("error", ""),
            token_count=token_count,
            priority=priority,
        )

        with self._lock:
            self._entries.append(entry)
            # 升级最近 N 步为 HIGH（不可被压缩）
            self._upgrade_recent()

        # 自动压缩
        if self.auto_compact:
            try:
                self.compact_if_needed()
            except Exception as e:  # noqa: BLE001
                logger.debug("自动压缩失败: %s", e)

        return entry

    def add_message(self, role: str, content: str,
                    priority: str = PRIORITY_NORMAL) -> ContextEntry:
        """添加一段对话消息（如 LLM messages 列表中的一条）。"""
        from kernel.pulse.cost_tracker import count_tokens

        entry = ContextEntry(
            id=uuid.uuid4().hex[:12],
            session_id=self.session_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            step_index=len(self._entries),
            step_name=f"message:{role}",
            capability="inference.llm",
            content=content,
            token_count=count_tokens(content),
            priority=priority,
        )
        with self._lock:
            self._entries.append(entry)
            self._upgrade_recent()
        return entry

    # ── 压缩 ──

    def total_tokens(self) -> int:
        """当前上下文总 token 数。"""
        return sum(e.token_count for e in self._entries)

    def compact_if_needed(self) -> Dict[str, Any]:
        """如果总 token 超过 max_tokens，压缩低优先级条目。

        压缩策略：
        1. 只压缩 priority=NORMAL 且 compacted=False 的条目
        2. 跳过最近 N 步（preserve_recent）和 CRITICAL 条目
        3. 把多个旧 NORMAL 条目合并成一个摘要条目

        Returns:
            压缩统计 {compacted, before_tokens, after_tokens, removed_count}
        """
        with self._lock:
            before_tokens = self.total_tokens()
            if before_tokens <= self.max_tokens:
                return {
                    "compacted": False,
                    "reason": "未超阈值",
                    "before_tokens": before_tokens,
                    "after_tokens": before_tokens,
                    "removed_count": 0,
                }

            # 找可压缩的条目（NORMAL + 已压缩过的不动 + 最近的保留）
            recent_ids = {e.id for e in self._entries[-self.preserve_recent:]}
            candidates = [
                e for e in self._entries
                if e.priority == PRIORITY_NORMAL
                and not e.compacted
                and e.id not in recent_ids
            ]

            if not candidates:
                return {
                    "compacted": False,
                    "reason": "无可压缩条目",
                    "before_tokens": before_tokens,
                    "after_tokens": before_tokens,
                    "removed_count": 0,
                }

            # 按时间顺序合并（最早的先压）
            candidates.sort(key=lambda e: e.step_index)

            # 合并成一个摘要
            removed_count = 0
            summary_parts = []
            for e in candidates:
                # 摘要：保留步骤名 + 关键输出片段（前 200 字符）
                snippet = (e.content or "")[:200]
                summary_parts.append(
                    f"[步骤{e.step_index}:{e.step_name}] {snippet}"
                )
                removed_count += 1

            # 创建摘要条目
            summary_text = f"【已压缩 {removed_count} 个旧步骤】\n" + "\n---\n".join(summary_parts)
            from kernel.pulse.cost_tracker import count_tokens
            summary_entry = ContextEntry(
                id=uuid.uuid4().hex[:12],
                session_id=self.session_id,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                step_index=candidates[0].step_index,
                step_name=f"compressed_summary_{removed_count}",
                capability="context.summary",
                content=summary_text,
                token_count=count_tokens(summary_text),
                priority=PRIORITY_LOW,  # 摘要优先级最低，下次压缩可再压
                compacted=True,
            )

            # 移除原条目，插入摘要
            candidate_ids = {e.id for e in candidates}
            self._entries = [
                summary_entry if e.id == candidates[0].id else e
                for e in self._entries
                if e.id not in candidate_ids or e.id == candidates[0].id
            ]
            # 实际上需要把 candidates[0] 替换成 summary，其余删除
            new_entries = []
            inserted_summary = False
            for e in self._entries:
                if e.id in candidate_ids:
                    if not inserted_summary:
                        new_entries.append(summary_entry)
                        inserted_summary = True
                    # 其余 candidate 跳过
                else:
                    new_entries.append(e)
            self._entries = new_entries

            after_tokens = self.total_tokens()

            return {
                "compacted": True,
                "reason": f"压缩了 {removed_count} 个旧步骤",
                "before_tokens": before_tokens,
                "after_tokens": after_tokens,
                "removed_count": removed_count,
                "saved_tokens": before_tokens - after_tokens,
            }

    def _upgrade_recent(self) -> None:
        """把最近 N 步的优先级升到 HIGH（不可被压缩），同时把不在最近 N 步的
        旧 HIGH 条目降回 NORMAL（窗口滑动后，旧条目不再受保护）。

        注意：CRITICAL（失败步骤）和 LOW（已压缩的摘要）不动——
        CRITICAL 永远保留，LOW 永远是摘要。
        """
        recent_ids = {id(e) for e in self._entries[-self.preserve_recent:]}
        for e in self._entries:
            if id(e) in recent_ids:
                if e.priority == PRIORITY_NORMAL:
                    e.priority = PRIORITY_HIGH
            else:
                # 窗口滑出：旧的 HIGH 降回 NORMAL（可被压缩）
                if e.priority == PRIORITY_HIGH:
                    e.priority = PRIORITY_NORMAL

    # ── 查询 ──

    def get_context_text(self, max_entries: int = 0) -> str:
        """获取当前上下文的文本表示（用于喂给 LLM）。

        Args:
            max_entries: 最多返回多少条（0=全部）
        """
        with self._lock:
            entries = list(self._entries)
        if max_entries > 0:
            entries = entries[-max_entries:]

        parts = []
        for e in entries:
            label = e.step_name or e.capability or "step"
            if e.compacted:
                parts.append(f"[摘要] {e.content}")
            elif e.ok:
                parts.append(f"[{label}] {e.content}")
            else:
                parts.append(f"[{label} ❌ {e.error}] {e.content}")
        return "\n\n".join(parts)

    def get_entries(self, priority: str = "") -> List[Dict[str, Any]]:
        """获取所有条目（可按优先级过滤）。"""
        with self._lock:
            entries = list(self._entries)
        if priority:
            entries = [e for e in entries if e.priority == priority]
        return [asdict(e) for e in entries]

    def stats(self) -> Dict[str, Any]:
        """获取上下文统计信息。"""
        with self._lock:
            entries = list(self._entries)
        total = len(entries)
        by_priority: Dict[str, int] = {}
        for e in entries:
            by_priority[e.priority] = by_priority.get(e.priority, 0) + 1
        return {
            "session_id": self.session_id,
            "total_entries": total,
            "total_tokens": self.total_tokens(),
            "max_tokens": self.max_tokens,
            "token_usage_pct": round(self.total_tokens() / self.max_tokens * 100, 1)
                if self.max_tokens > 0 else 0,
            "by_priority": by_priority,
            "compacted_count": sum(1 for e in entries if e.compacted),
            "created_at": self._created_at,
        }

    # ── 持久化 ──

    def persist(self) -> str:
        """把当前会话上下文持久化到 JSONL（断点续跑用）。

        Returns:
            持久化文件路径
        """
        path = _session_path(self.session_id)
        try:
            with self._lock:
                entries = list(self._entries)
            with open(path, "w", encoding="utf-8") as f:
                # 先写一个 header
                header = {
                    "type": "session_header",
                    "session_id": self.session_id,
                    "created_at": self._created_at,
                    "persisted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "max_tokens": self.max_tokens,
                    "entry_count": len(entries),
                }
                f.write(json.dumps(header, ensure_ascii=False) + "\n")
                for e in entries:
                    f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
            return path
        except Exception as e:  # noqa: BLE001
            logger.warning("持久化上下文失败: %s", e)
            return ""

    @classmethod
    def load(cls, session_id: str) -> Optional["ContextManager"]:
        """从持久化文件加载一个会话上下文（断点续跑）。"""
        path = _session_path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if not lines:
                return None

            # 解析 header
            header = json.loads(lines[0].strip())
            if header.get("type") != "session_header":
                return None

            manager = cls(
                session_id=header.get("session_id", session_id),
                max_tokens=header.get("max_tokens", 8000),
                auto_compact=False,  # 加载时不要自动压缩
            )
            manager._created_at = header.get("created_at", "")

            # 加载所有 entries
            for line in lines[1:]:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = ContextEntry(**data)
                    manager._entries.append(entry)
                except (json.JSONDecodeError, TypeError):
                    continue

            return manager
        except Exception as e:  # noqa: BLE001
            logger.warning("加载上下文失败: %s", e)
            return None

    def clear(self) -> None:
        """清空当前会话上下文。"""
        with self._lock:
            self._entries.clear()

    # ── 内部 ──

    def _extract_text(self, step_result: Dict[str, Any]) -> str:
        """从步骤结果提取文本内容。"""
        parts = []
        # step_name + capability
        if step_result.get("step_name"):
            parts.append(f"步骤: {step_result['step_name']}")
        if step_result.get("capability"):
            parts.append(f"能力: {step_result['capability']}")

        # output 内容
        out = step_result.get("output") or {}
        if isinstance(out, dict):
            for k in ("content", "output", "result", "text", "response", "answer"):
                v = out.get(k)
                if isinstance(v, str) and v:
                    parts.append(v)
                elif isinstance(v, dict):
                    for sub_k in ("content", "output", "text"):
                        sv = v.get(sub_k)
                        if isinstance(sv, str) and sv:
                            parts.append(sv)
            # 如果没有上面那些字段，把整个 output 转成字符串（截断）
            if not any(out.get(k) for k in ("content", "output", "result", "text", "response", "answer")):
                try:
                    s = json.dumps(out, ensure_ascii=False)
                    if len(s) > 500:
                        s = s[:500] + "..."
                    parts.append(s)
                except Exception:
                    pass
        elif isinstance(out, str):
            parts.append(out)

        # error
        if step_result.get("error"):
            parts.append(f"错误: {step_result['error']}")

        return "\n".join(parts)


# ── 全局会话注册表（多会话管理）──

_sessions: Dict[str, ContextManager] = {}
_sessions_lock = threading.Lock()


def get_session(session_id: str, max_tokens: int = 8000) -> ContextManager:
    """获取或创建一个会话上下文（单例 per session_id）。"""
    with _sessions_lock:
        if session_id not in _sessions:
            _sessions[session_id] = ContextManager(
                session_id=session_id, max_tokens=max_tokens,
            )
        return _sessions[session_id]


def list_sessions() -> List[Dict[str, Any]]:
    """列出所有活跃会话。"""
    with _sessions_lock:
        return [m.stats() for m in _sessions.values()]


def delete_session(session_id: str) -> bool:
    """删除一个会话（从内存和磁盘）。"""
    with _sessions_lock:
        existed = session_id in _sessions
        if existed:
            del _sessions[session_id]
    # 删磁盘
    path = _session_path(session_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:  # noqa: BLE001
            logger.debug("删除会话文件失败: %s", e)
            return False
    return existed or os.path.exists(path) is False


def reset_sessions_for_test() -> None:
    """测试辅助：清空所有会话。"""
    with _sessions_lock:
        _sessions.clear()
