"""子进程隔离 worker（B 路线，已收口）。

作为一个**独立 Python 子进程**运行，监听本地传输通道（默认 Windows Named Pipe /
AF_PIPE；沙箱等不支持 Named Pipe 的环境可退化为 TCP loopback），加载一个**真实**
fabric 适配器，循环处理来自父进程（内核/枢纽）的调用请求。

这是 Chiplet「故障隔离 + 独立地址空间封装」在软件里的直接对应：把单个芯粒装进
独立进程，它崩溃/OOM 不影响宿主内核与其他芯粒。

由 SubprocessIsolationLayer / IsolatedEngineHost 内部拉起，正常无需手动调用：
    python -m kernel.isolation.worker --transport pipe --addr <name> [--adapter mod:Cls]
    python -m kernel.isolation.worker --transport tcp  --addr 127.0.0.1:54321
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time

# 轻量 import：仅保证能解析报文。合成芯粒不依赖任何重引擎/网络。
_src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.environ.get("AOS_SRC", _src_dir))


def _make_synthetic_handler(task_us: float):
    """合成芯粒：默认零工作（RTT 只含 IPC + (反)序列化开销）。

    --task-us>0 时微秒级忙等，用于模拟「轻任务」对 RTT 的影响。
    """

    def handler(msg: dict) -> dict:
        payload = msg.get("payload") or {}
        if task_us > 0:
            deadline = time.perf_counter() + task_us / 1_000_000.0
            while time.perf_counter() < deadline:
                pass
        return {"ok": True,
                "data": {"echo": payload, "pid": os.getpid(),
                         "t": time.perf_counter()},
                "error": None}

    return handler


def _load_adapter(spec: str | None, task_us: float):
    """spec: 'module.path:ClassName'。

    返回 (handler_callable, capabilities)。handler 接收完整 msg dict，
    返回 {ok,data,error} 形状的响应（由 main 循环直接 send）。

    真实适配器集成（B 路线收口）：动态 import 指定类 → 实例化 →
    把 IPC 报文 (capability 字符串 + payload) 翻译成 InvokeRequest，
    调 adapter.invoke()，再把 InvokeResult 翻回 {ok,data,error}。
    这样 worker 能托管任意 BaseAgentAdapter，且崩溃只发生在子进程内。
    """
    if not spec:
        return _make_synthetic_handler(task_us), ["bench.ping"]

    mod_name, _, cls_name = spec.rpartition(":")
    if not mod_name or not cls_name:
        raise ValueError(f"非法 adapter spec: {spec!r}（应为 'module:Class'）")
    mod = importlib.import_module(mod_name)
    cls = getattr(mod, cls_name)
    adapter = cls()
    caps = [c.value if hasattr(c, "value") else str(c)
            for c in adapter.advertise_capabilities()]

    from core.fabric.adapter import InvokeRequest
    from core.fabric.capability import Capability

    def handler(msg: dict) -> dict:
        cap_str = msg.get("capability")
        payload = msg.get("payload") or {}
        try:
            cap = Capability(cap_str)
        except Exception:  # noqa: BLE001 - 未知能力串原样下传，由适配器决定
            cap = cap_str
        req = InvokeRequest(capability=cap, payload=payload)
        res = adapter.invoke(req)
        return {"ok": res.ok, "data": res.data, "error": res.error}

    return handler, caps


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
    conn = listener.accept()  # 阻塞直到父进程（隔离层）连接
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
            # 真实调用（handler 自己返回 {ok,data,error}）
            try:
                conn.send(handler(msg))
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
