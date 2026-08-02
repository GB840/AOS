"""
chiplet_sandbox.py —— 芯粒快照续跑沙箱（② 级轻量原型）

借鉴来源：openEuler Agentic Infra 的 **Conch 沙箱引擎**
（AI Agent 完整沙箱镜像 + 快照冷启动 / 迁移 / 续跑）+ **Agent POSIX 原语**。
对齐 AOS 现有：agnes/ag2 子进程 crash boundary（芯粒故障隔离）+ `isolate_heavy`。

诚实边界（必读）：
- 本模块为 **原型骨架**，用本地 pickle 状态序列化模拟「芯粒快照 / 续跑」，
  不调用真实容器 / 虚拟机，不接真 LLM。
- 仅验证「快照 → 崩溃 → 从快照恢复续跑」的控制流可跑通（② 级），
  不等同 openEuler Conch 的完整沙箱镜像 / 迁移能力（③ 级端到端）。
- 生产化路径：把 `_snapshots` 换成轻量容器（如 containerd/runsc）的
  镜像快照 + CRIU 检查点，即接近 Conch 的真实续跑；当前仅留接口与单测。
"""
from __future__ import annotations

import pickle
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


@dataclass
class ChipletState:
    """芯粒运行态（可序列化快照）。"""

    chiplet_id: str
    step: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    snapshot_id: Optional[str] = None


class ChipletCrashed(Exception):
    """芯粒在 crash boundary 崩溃（携带续跑快照 id）。"""

    def __init__(self, snapshot_id: str) -> None:
        super().__init__(f"chiplet crashed; resume from {snapshot_id}")
        self.snapshot_id = snapshot_id


class ChipletSandbox:
    """芯粒快照续跑沙箱（原型）。

    对齐 openEuler Conch 的「快照冷启 / 迁移 / 续跑」理念：
    芯粒在 crash boundary 崩溃前自动留快照，之后可从快照恢复续跑，
    不让长任务因单次崩溃而整体重来。
    """

    def __init__(self) -> None:
        self._snapshots: Dict[str, bytes] = {}

    def snapshot(self, state: ChipletState) -> str:
        """对芯粒运行态打快照，返回 snapshot_id。"""
        sid = state.snapshot_id or uuid.uuid4().hex[:12]
        state.snapshot_id = sid
        self._snapshots[sid] = pickle.dumps(state)
        return sid

    def resume(self, snapshot_id: str) -> ChipletState:
        """从快照恢复芯粒运行态（续跑前调用）。"""
        if snapshot_id not in self._snapshots:
            raise KeyError(f"快照不存在：{snapshot_id}")
        return pickle.loads(self._snapshots[snapshot_id])

    def run(
        self,
        chiplet_fn: Callable[[ChipletState], ChipletState],
        init: Optional[ChipletState] = None,
        snapshot_id: Optional[str] = None,
        crash_at_step: Optional[int] = None,
    ) -> ChipletState:
        """执行芯粒；支持从快照续跑；可注入崩溃点模拟 crash boundary。

        - snapshot_id 给定时从快照恢复（续跑模式）。
        - crash_at_step 给定时在该 step 模拟崩溃（崩溃前自动留快照）。
        """
        if snapshot_id:
            state = self.resume(snapshot_id)
        else:
            state = init or ChipletState(chiplet_id=uuid.uuid4().hex[:8])

        max_steps = state.data.get("max_steps", 3)
        while state.step < max_steps:
            if crash_at_step is not None and state.step == crash_at_step:
                # 模拟芯粒在 crash boundary 崩溃（agnes/ag2 子进程边界）
                self.snapshot(state)  # 崩溃前自动留快照，供续跑
                raise ChipletCrashed(state.snapshot_id)
            state = chiplet_fn(state)
            state.step += 1
        self.snapshot(state)
        return state
