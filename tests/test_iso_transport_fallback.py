"""隔离传输自动退避：本环境不支持 Named Pipe 时，透明退 tcp 且隔离仍真生效。

锁死 B 路线两个易碎点：
  1. 传输探测 `_pipe_supported()` 在 Named Pipe 不可用时返回 False；
  2. 显式 transport="pipe" 也能自动降级为 tcp，且仍真进子进程（进程外铁证）。

这样用户无需手动 set AOS_ISO_TRANSPORT，沙箱 / 部分 pwsh 主机都能跑通隔离。
"""
from __future__ import annotations

import os
import sys

REPO_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if REPO_SRC not in sys.path:
    sys.path.insert(0, REPO_SRC)

from kernel.isolation import subprocess_iso  # noqa: E402
from kernel.isolation._bench_adapter import BenchRealAdapter  # noqa: E402
from kernel.isolation.subprocess_iso import IsolatedEngineHost  # noqa: E402


BENCH_SPEC = "kernel.isolation._bench_adapter:BenchRealAdapter"


def test_pipe_unsupported_detected(monkeypatch):
    """探测函数在本环境（Named Pipe 被禁）应返回 False。"""
    monkeypatch.setattr(subprocess_iso, "_pipe_supported", lambda: False)
    assert subprocess_iso._pipe_supported() is False


def test_explicit_pipe_auto_falls_back_to_tcp(monkeypatch):
    """显式 transport='pipe' 但本环境不支持 → 自动退 tcp，且隔离真生效。"""
    # 强制认为 Named Pipe 不可用，模拟沙箱 / 部分 pwsh 主机。
    monkeypatch.setattr(subprocess_iso, "_pipe_supported", lambda: False)

    host = IsolatedEngineHost(
        engine_id="bench",
        adapter_spec=BENCH_SPEC,
        transport="pipe",  # 故意指定 pipe，触发自动退避
        standby=False,
    )
    try:
        host.start()
        # 1) 传输确实退到了 tcp
        assert host._transport == "tcp", \
            f"pipe 不可用时应自动退 tcp，实际={host._transport}"
        # 2) 隔离仍真进子进程（进程外铁证）
        pid = host.subprocess_pid
        assert pid is not None, "退避后子进程应正常拉起"
        assert pid != os.getpid(), "subprocess_pid == 宿主 PID → 隔离失效"
        # 3) 真能经 IPC 调用
        res = host.invoke("bench.ping", {"x": 1})
        assert res.get("ok") is True, f"隔离子进程调用失败: {res}"
    finally:
        host.stop()
