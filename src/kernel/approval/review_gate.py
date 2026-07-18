"""步骤级审核闸门（三省六部制式「封驳」）。

把「敏感步骤执行前需人工准/驳」真正接进 OrchestrationChiplet 的执行路径：

- 复用既有 ApprovalStore（kernel.approval.approval_store，JSONL 单例、可审计）
  作为「单一真相」，不另造审批存储；
- 调度层在 _run_step 执行前咨询本闸门：
    * pending / 无决策 → 挡住执行，落 awaiting_review（不执行、不伪造）；
    * approved      → 放行，继续正常执行；
    * rejected      → 封驳，不执行、标记 rejected。
- 准/驳经现有 /api/approvals 完成（approval_api 已写好、本次挂载）；
- 准后由 /api/review/resume/{run_id} 用持久化 spec 重新拉起流水线（闭环）。

设计原则（对齐 AGENTS.md）：
- 模块级单例 get_review_gate()；OrchestrationChiplet 仅在 spec["review_mode"]=="gate"
  时取用；**不开启则完全无副作用**（理念1 自闭环 + 对现有链路零回归）。
- best-effort：审批模块不可用时闸门自动降级为 None（不阻断主流程，理念6 诚实）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional, Tuple

# 敏感能力集：命中即需审核（即便未显式标 requires_approval）。
# 仅含明确「会改状态/执行副作用」的能力，避免误伤纯查询。
_SENSITIVE_CAPS = {
    "code.generate", "code.exec", "code.execute",
    "file.write", "file.delete", "file.remove",
    "shell.exec", "system.execute", "db.write", "web.write",
}


def _as_str(cap) -> str:
    return cap.value if hasattr(cap, "value") else str(cap)


def _approval_store():
    from kernel.approval.approval_store import get_approval_store
    return get_approval_store()


def _specs_path() -> str:
    base = os.environ.get(
        "AOS_RESUME_SPECS_PATH",
        os.path.join("data", "workspaces", "fabric", "resume_specs.jsonl"),
    )
    os.makedirs(os.path.dirname(base) or ".", exist_ok=True)
    return base


class ReviewGate:
    """步骤级审核闸门：把「准/驳」接进编排执行流。

    单例（get_review_gate）。线程安全（spec 读写过锁）。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._specs_file = _specs_path()

    # ── 是否需审核 ──

    def should_review(self, step: Dict[str, Any]) -> bool:
        """该步是否需进入审核闸门。命中任一即需审核。"""
        if step.get("requires_approval") is True:
            return True
        risk = step.get("approval_risk")
        if risk == "high":
            return True
        cap = step.get("capability")
        if cap and _as_str(cap) in _SENSITIVE_CAPS:
            return True
        return False

    # ── 查/建 审批 ──

    def get_for_run_step(self, run_id: str, step_index: int) -> Optional[Dict[str, Any]]:
        """按 (run_id, step_index) 查已有审批（幂等，避免重复建 pending）。"""
        try:
            store = _approval_store()
        except Exception:  # noqa: BLE001
            return None
        for a in store.list_all():
            if a.run_id != run_id:
                continue
            if (a.payload or {}).get("step_index") == step_index:
                return a.to_dict()
        return None

    def resolve(self, run_id: str, step_index: int,
                step: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
        """决策一个步骤。

        返回 (decision, approval_dict)：
          - "execute"：已批准，放行执行；
          - "reject" ：已驳回，封驳不执行；
          - "await"  ：pending 或尚未决策，挡住执行（调用方应标记为 awaiting_review）。
        """
        existing = self.get_for_run_step(run_id, step_index)
        if existing:
            st = existing.get("status")
            if st == "approved":
                return "execute", existing
            if st == "rejected":
                return "reject", existing
            return "await", existing  # pending / expired → 仍挡住
        # 首次遇到：建 pending 审批（幂等由 get_for_run_step 保证）
        try:
            store = _approval_store()
        except Exception as e:  # noqa: BLE001
            logger.warning("审核存储不可用，步骤将放行(降级): %s", e)
            return "execute", None
        cap = _as_str(step.get("capability") or "?")
        risk = step.get("approval_risk")
        if risk not in ("low", "medium", "high"):
            risk = "high" if step.get("requires_approval") else "medium"
        ap = store.create_approval(
            source="orchestrator",
            title=f"步骤{step_index} 审核：{cap}",
            description=f"流水线步骤执行前需人工准/驳（capability={cap}）",
            risk_level=risk,
            payload={"run_id": run_id, "step_index": step_index, "capability": cap},
            run_id=run_id,
        )
        return "await", ap.to_dict()

    # ── resume 规格持久化（准后重新拉起流水线用）──

    def persist_spec(self, run_id: str, spec: Dict[str, Any]) -> None:
        with self._lock:
            specs = self._load_specs()
            specs[run_id] = {
                "spec": spec,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            self._save_specs(specs)

    def get_spec(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self._load_specs().get(run_id, {}).get("spec")

    def _load_specs(self) -> Dict[str, Any]:
        try:
            with open(self._specs_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_specs(self, d: Dict[str, Any]) -> None:
        tmp = self._specs_file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._specs_file)
        except OSError:
            pass


# ── 单例 ──

_gate: Optional["ReviewGate"] = None
_gate_lock = threading.Lock()


def get_review_gate() -> "ReviewGate":
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = ReviewGate()
    return _gate


# 延迟 import 避免循环；logger 在模块级可用
import logging  # noqa: E402
logger = logging.getLogger(__name__)
