"""Human-in-the-Loop 审批模块（Task 4）。

落地理念5「能力即路由，权限即边界」+ 理念2.5「反思闭环」：
- 任何模块（Evolve / WorkflowRunner / Autopilot）都可发起审批请求
- 中高风险操作不直接执行，进入 pending 队列等人工确认
- 审批通过后调用方从暂停处继续（中断恢复）

设计原则（Ponytail §10）：
- 复用现有：Evolve 已有 list_pending_approvals/approve_proposal——本模块是
  更通用的 ApprovalStore，Evolve 的高风险提案可经此统一暴露
- 标准 JSONL 持久化：跨进程可读、可审计
- 非侵入：调用方按需 create_approval；不调用 = 无副作用

数据落盘：data/workspaces/fabric/approvals.jsonl
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


def _approvals_path() -> str:
    base = os.environ.get(
        "AOS_APPROVALS_PATH",
        os.path.join("data", "workspaces", "fabric", "approvals.jsonl"),
    )
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    return base


@dataclass
class ApprovalRequest:
    """一个审批请求。"""
    id: str = ""
    source: str = ""              # 发起方：evolve / workflow_runner / autopilot / autoskill ...
    title: str = ""               # 人话标题
    description: str = ""         # 详情（变更内容、影响范围）
    risk_level: str = "medium"    # low / medium / high
    payload: Dict[str, Any] = field(default_factory=dict)  # 审批通过后执行所需数据
    # 状态：pending / approved / rejected / expired
    status: str = "pending"
    created_at: str = ""
    decided_at: str = ""
    decided_by: str = ""          # 审批人
    decision_note: str = ""       # 审批备注
    # 关联资源（可选）：让前端能跳转到对应工作流/提案
    workflow_id: str = ""
    run_id: str = ""
    proposal_id: str = ""         # Evolve 提案 ID（如有）
    # 过期时间（秒，0=永不过期）：避免长期 pending 占满队列
    ttl_seconds: int = 0
    expires_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ApprovalRequest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ApprovalStore:
    """审批请求的存储与管理。

    单例（get_approval_store()），所有模块共用同一份 JSONL。
    并发安全：所有读写都过 _lock。
    """

    def __init__(self, path: str = ""):
        self._path = path or _approvals_path()
        self._lock = threading.RLock()
        self._cache: Optional[List[ApprovalRequest]] = None
        # 确保 file 存在
        if not os.path.exists(self._path):
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            open(self._path, "a", encoding="utf-8").close()

    # ── 基础 IO ──

    def _load(self) -> List[ApprovalRequest]:
        if self._cache is not None:
            return self._cache
        items: List[ApprovalRequest] = []
        try:
            with self._lock:
                with open(self._path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            items.append(ApprovalRequest.from_dict(json.loads(line)))
                        except (json.JSONDecodeError, TypeError):
                            continue
        except OSError as e:
            logger.warning("读取审批队列失败: %s", e)
        self._cache = items
        return items

    def _persist(self) -> None:
        items = self._cache or []
        tmp = self._path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for a in items:
                f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
        os.replace(tmp, self._path)

    def _append(self, approval: ApprovalRequest) -> None:
        """单条追加（写优化：审批创建是高频操作）。"""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(approval.to_dict(), ensure_ascii=False) + "\n")
        if self._cache is not None:
            self._cache.append(approval)

    def _invalidate(self) -> None:
        self._cache = None

    # ── 公开 API ──

    def create_approval(
        self,
        *,
        source: str,
        title: str,
        description: str = "",
        risk_level: str = "medium",
        payload: Dict[str, Any] = None,
        workflow_id: str = "",
        run_id: str = "",
        proposal_id: str = "",
        ttl_seconds: int = 0,
    ) -> ApprovalRequest:
        """创建一个审批请求。返回创建的 ApprovalRequest（含 id）。

        风险等级语义（与 Evolve 对齐）：
        - low: 自动应用（不进 pending 队列，仅记录）
        - medium: 进入 pending 队列等审批
        - high: 必须人工确认，且通常需要额外信息（如双签）
        """
        approval = ApprovalRequest(
            id=uuid.uuid4().hex[:12],
            source=source,
            title=title,
            description=description,
            risk_level=risk_level,
            payload=payload or {},
            workflow_id=workflow_id,
            run_id=run_id,
            proposal_id=proposal_id,
            ttl_seconds=ttl_seconds,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            # 注意：用 localtime（与 list_pending 的 mktime 配对，避免 UTC 与本地时差）
            expires_at=(
                time.strftime("%Y-%m-%dT%H:%M:%S",
                              time.localtime(time.time() + ttl_seconds))
                if ttl_seconds > 0 else ""
            ),
        )
        with self._lock:
            self._append(approval)
        logger.info("审批请求已创建 [%s] %s (risk=%s)",
                    approval.id, approval.title, approval.risk_level)
        return approval

    def list_pending(self, source: str = "",
                     risk_level: str = "",
                     limit: int = 100) -> List[ApprovalRequest]:
        """列出待审批请求。

        排序：高风险优先，同风险按创建时间倒序（最新在前）。
        """
        items = self._load()
        now = time.time()
        result = []
        for a in items:
            if a.status != "pending":
                continue
            if source and a.source != source:
                continue
            if risk_level and a.risk_level != risk_level:
                continue
            if a.expires_at:
                try:
                    exp_ts = time.mktime(time.strptime(
                        a.expires_at[:19], "%Y-%m-%dT%H:%M:%S"))
                    if exp_ts < now:
                        continue
                except (ValueError, OverflowError):
                    pass
            result.append(a)

        def _sort_key(a: ApprovalRequest):
            risk_order = {"high": 0, "medium": 1, "low": 2}
            try:
                ts = time.mktime(time.strptime(
                    (a.created_at or "2000-01-01T00:00:00")[:19],
                    "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, OverflowError):
                ts = 0.0
            # risk 升序（high 在前），ts 倒序（新在前 → 用负数）
            return (risk_order.get(a.risk_level, 9), -ts)

        result.sort(key=_sort_key)
        return result[:limit]

    def list_all(self, status: str = "", source: str = "",
                 limit: int = 100) -> List[ApprovalRequest]:
        """列出所有审批请求（含历史），可按 status/source 过滤。"""
        items = self._load()
        result = []
        for a in items:
            if status and a.status != status:
                continue
            if source and a.source != source:
                continue
            result.append(a)
        # 按 created_at 倒序
        result.sort(key=lambda x: x.created_at, reverse=True)
        return result[:limit]

    def get(self, approval_id: str) -> Optional[ApprovalRequest]:
        """按 id 获取审批请求。"""
        for a in self._load():
            if a.id == approval_id:
                return a
        return None

    def get_by_proposal(self, proposal_id: str) -> Optional[ApprovalRequest]:
        """按 proposal_id 查找审批请求（Evolve 提案同步用）。"""
        if not proposal_id:
            return None
        for a in self._load():
            if a.proposal_id == proposal_id:
                return a
        return None

    def _post_decision_hook(self, approval: ApprovalRequest, *, action: str,
                            decided_by: str = "", note: str = "") -> None:
        """审批决策后的钩子——回调对应源系统执行真正的操作。

        - evolve: 回调 EvolveEngine 应用/拒绝提案
        """
        try:
            if approval.source == "evolve" and approval.proposal_id:
                from kernel.evolve.evolve_engine import get_evolve_engine
                engine = get_evolve_engine()
                if action == "approve":
                    engine.approve_proposal(approval.proposal_id)
                elif action == "reject":
                    engine.reject_proposal(approval.proposal_id, reason=note)
        except Exception as e:  # noqa: BLE001
            logger.warning("审批决策钩子执行失败 [%s]: %s", approval.id, e)

    def approve(self, approval_id: str, decided_by: str = "",
                note: str = "") -> Dict[str, Any]:
        """批准一个审批请求。

        返回 {ok, approval, error}。
        - 找不到：ok=False, error="不存在"
        - 状态非 pending：ok=False, error="已决策"
        - 成功：ok=True, approval=更新后的 ApprovalRequest
        """
        decided_item = None
        result: Dict[str, Any] = {}
        with self._lock:
            items = self._load()
            for i, a in enumerate(items):
                if a.id != approval_id:
                    continue
                if a.status != "pending":
                    return {"ok": False, "error": f"已决策为 {a.status}",
                            "approval": a.to_dict()}
                a.status = "approved"
                a.decided_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                a.decided_by = decided_by
                a.decision_note = note
                items[i] = a
                self._cache = items
                self._persist()
                logger.info("审批已批准 [%s] by=%s", approval_id, decided_by)
                decided_item = a
                result = {"ok": True, "approval": a.to_dict(), "error": ""}
                break
            else:
                return {"ok": False, "error": f"审批不存在: {approval_id}"}
        # 钩子在锁外调用，避免长时间持锁 / 死锁
        if decided_item is not None:
            self._post_decision_hook(decided_item, action="approve",
                                     decided_by=decided_by, note=note)
        return result

    def reject(self, approval_id: str, decided_by: str = "",
               note: str = "") -> Dict[str, Any]:
        """拒绝一个审批请求。"""
        decided_item = None
        result: Dict[str, Any] = {}
        with self._lock:
            items = self._load()
            for i, a in enumerate(items):
                if a.id != approval_id:
                    continue
                if a.status != "pending":
                    return {"ok": False, "error": f"已决策为 {a.status}",
                            "approval": a.to_dict()}
                a.status = "rejected"
                a.decided_at = time.strftime("%Y-%m-%dT%H:%M:%S")
                a.decided_by = decided_by
                a.decision_note = note
                items[i] = a
                self._cache = items
                self._persist()
                logger.info("审批已拒绝 [%s] by=%s", approval_id, decided_by)
                decided_item = a
                result = {"ok": True, "approval": a.to_dict(), "error": ""}
                break
            else:
                return {"ok": False, "error": f"审批不存在: {approval_id}"}
        # 钩子在锁外调用
        if decided_item is not None:
            self._post_decision_hook(decided_item, action="reject",
                                     decided_by=decided_by, note=note)
        return result

    def delete(self, approval_id: str) -> bool:
        """物理删除一个审批请求（管理员操作）。"""
        with self._lock:
            items = self._load()
            new_items = [a for a in items if a.id != approval_id]
            if len(new_items) == len(items):
                return False
            self._cache = new_items
            self._persist()
            return True

    def stats(self) -> Dict[str, int]:
        """返回各状态计数（可观测）。"""
        items = self._load()
        stats = {"pending": 0, "approved": 0, "rejected": 0, "total": len(items)}
        for a in items:
            if a.status in stats:
                stats[a.status] += 1
        return stats


# ── 单例 ──

_store: Optional[ApprovalStore] = None
_store_lock = threading.Lock()


def get_approval_store() -> ApprovalStore:
    """获取全局 ApprovalStore 单例。"""
    global _store
    with _store_lock:
        if _store is None:
            _store = ApprovalStore()
    return _store
