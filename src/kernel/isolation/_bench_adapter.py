"""隔离层测试用的轻量真实适配器 fixture（仅 B 路线收口测试使用）。

刻意零依赖、零网络：证明「worker 能托管一个真正的 BaseAgentAdapter 并在子进程内
执行 invoke」——响应里带回子进程 os.getpid()，即可在测试中断言「确实跑在另一个
进程地址空间」。不作为正式 fabric 引擎注册。
"""
from __future__ import annotations

import os

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability


class BenchRealAdapter(BaseAgentAdapter):
    """进程内/进程外行为一致的基准适配器；用于验证隔离层是否真在子进程执行。"""

    @property
    def engine_id(self) -> str:
        return "bench_real"

    def advertise_capabilities(self):
        return [Capability.BENCH_ISOLATE, Capability.BENCH_PING]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        return InvokeResult(
            ok=True,
            data={
                "pid": os.getpid(),          # 子进程 PID —— 隔离的关键证据
                "cap": req.capability.value if hasattr(req.capability, "value")
                       else str(req.capability),
                "echo": req.payload,
            },
        )

    def health(self) -> bool:
        return True
