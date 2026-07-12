"""子进程隔离 worker（B 路线 PoC）。

作为一个**独立 Python 子进程**运行，监听本地传输通道（默认 Windows Named Pipe /
AF_PIPE；沙箱等不支持 Named Pipe 的环境可退化为 TCP loopback），加载一个 fabric
芯粒，循环处理来自父进程（内核/枢纽）的调用请求。

这是 Chiplet「故障隔离 + 独立地址空间封装」在软件里的直接对应：把单个芯粒装进
独立进程，它崩溃/OOM 不影响宿主内核与其他芯粒。

由 SubprocessIsolationLayer 内部拉起，正常无需手动调用：
    python -m kernel.isolation.worker --transport pipe --addr <name>
    python -m kernel.isolation.worker --transport tcp  --addr 127.0.0.1:54321
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# 轻量 import：仅保证能解析报文。合成芯粒不依赖任何重引擎/网络。
sys.path.insert(0, os.environ.get("AOS_SRC", "D:/AOS/src"))


def _make_synthetic_handler(task_us: float):
    """合成芯粒：默认零工作（RTT 只含 IPC + (反)序列化开销）。

    --task-us>0 时微秒级忙等，用于模拟「轻任务」对 RTT 的影响。
    """

    def handler(payload: dict) -> dict:
        if task_us > 0:
            deadline = time.perf_counter() + task_us / 1_000_000.0
            while time.perf_counter() < deadline:
                pass
        return {"echo": payload, "pid": os.getpid(), "t": time.perf_counter()}

    return handler


def _load_adapter(spec: str | None, task_us: float):
    """spec: 'module.path:ClassName'。

    返回 (handler_callable, capabilities)。handler 接收 payload dict，
    返回 data dict。真实适配器集成阶段在此动态 import 并包裹 adapter.invoke；
    本 PoC 默认合成 handler，刻意不引入重依赖以测出「纯隔离开销」。
    """
    if not spec:
        return _make_synthetic_handler(task_us), ["bench.ping"]
    # TODO(集成): 动态 import 真实适配器并包裹成 handler。PoC 阶段保持轻量。
    raise NotImplementedError("真实适配器动态加载留待集成阶段（B 路线收口时实现）")


def _parse_addr(transport: str, addr: str):
    if transport == "tcp":
        host, port = addr.split(":")
        return (host, int(port))
    return addr  # pipe: 名字字符串


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transport", default="pipe", choices=["pipe", "tcp"])
    ap.add_argument("--addr", required=True, help="pipe 名 或 127.0.0.1:port")
    ap.add_argument("--adapter", default=None, help="module.path:ClassName")
    ap.add_argument("--task-us", type=float, default=0.0, help="合成芯粒微秒级忙等")
    args = ap.parse_args()

    from multiprocessing.connection import Listener

    handler, caps = _load_adapter(args.adapter, args.task_us)
    family = "AF_INET" if args.transport == "tcp" else "AF_PIPE"
    address = _parse_addr(args.transport, args.addr)

    listener = Listener(address, family=family)
    conn = listener.accept()  # 阻塞直到父进程（SubprocessIsolationLayer）连接
    try:
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                break  # 父进程断开 → 优雅退出
            if not isinstance(msg, dict):
                conn.send({"ok": False, "error": "bad message", "data": None})
                continue
            if msg.get("__ctrl") == "ping":
                conn.send({"ok": True, "data": {"pong": True}, "error": None})
                continue
            # 真实调用
            try:
                data = handler(msg.get("payload") or {})
                conn.send({"ok": True, "data": data, "error": None})
            except Exception as e:  # noqa: BLE001
                conn.send({"ok": False, "error": repr(e), "data": None})
    finally:
        try:
            conn.close()
        finally:
            listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
