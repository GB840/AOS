"""子进程隔离（B 路线 PoC）包。

把单个 fabric 芯粒装进独立进程，经 Windows Named Pipe 通信，
用于验证「进程级故障隔离」是否可行（spawn/RTT/recovery 三闸门）。
"""
from .subprocess_iso import (
    SubprocessIsolationLayer,
    GATE_SPAWN_MS,
    GATE_RTT_US,
    GATE_RECOVER_MS,
)

__all__ = [
    "SubprocessIsolationLayer",
    "GATE_SPAWN_MS",
    "GATE_RTT_US",
    "GATE_RECOVER_MS",
]
