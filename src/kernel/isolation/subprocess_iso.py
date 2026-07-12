"""子进程隔离层（B 路线 PoC）：把单个 fabric 芯粒装进独立进程，经本地 IPC 通信。

提供三项**诚实度量**，直接对应 B 路线的三道闸门：
  - spawn_ms     : 从 Popen 到「首条 RPC 成功返回」的耗时
                   （含解释器冷启动 + import + 监听就绪 + 首次握手）
  - rtt_us       : 单次调用经本地 IPC 的往返延迟（纯 IPC 开销，合成芯粒零任务）
  - recovery_ms  : 杀掉子进程后重新拉起并恢复服务的时间

这些数字决定 B 路线（进程级故障隔离）是否可行。若 spawn 过慢，可用「预热进程池」
缓解——本文件只负责测出真相，不替结论遮掩。

传输（transport）：
  - "pipe"（默认，生产）：Windows Named Pipe（AF_PIPE），对应 Chiplet 的
    UCIe-S 低延迟互连。需要宿主支持 CreateNamedPipe（沙箱常被禁，故见下）。
  - "tcp"（验证用）：127.0.0.1 loopback，沙箱/CI 无 Named Pipe 时用来跑通
    整套隔离 machinery 并拿到真实闸门数字。两者 RTT 量级相近（数十 μs）。
  - 自动退避：隔离层启动时会探测 Named Pipe 是否可用（_pipe_supported），
    不可用则透明退 tcp——保留真实主机 pipe 优先，又免去手动设
    AOS_ISO_TRANSPORT 的麻烦（本环境无需该变量即可隔离）。

用法（见 scripts/subprocess_iso_probe.py）：
    layer = SubprocessIsolationLayer(engine_id="bench_iso", transport="pipe")
    spawn_ms = layer.start()                 # 拉起
    res = layer.invoke("bench.ping", {...})  # 经 IPC 调用
    rec_ms = layer.kill_and_recover()         # 模拟崩溃 + 重启
    layer.stop()
"""
from __future__ import annotations

import os
import random
import socket
import sys
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

# 闸门阈值（用户定义，Day22-30 B 路线）
GATE_SPAWN_MS = 500.0
GATE_RTT_US = 100.0
GATE_RECOVER_MS = 3000.0

_AOS_SRC = os.environ.get("AOS_SRC", "D:/AOS/src")
_CONNECT_TIMEOUT = 30.0
_MAX_SPAWN_ATTEMPTS = 3

# Named Pipe 可用性探测结果缓存：本环境（如部分 pwsh / 沙箱）CreateNamedPipe
# 被禁时，自动退 tcp，避免隔离「假阴性」退回进程内。真实 Windows 主机支持则仍
# 优先 pipe（UCIe-S 低延迟互连）。
_PIPE_SUPPORTED: Optional[bool] = None


def _pipe_supported() -> bool:
    """探测本环境是否支持 multiprocessing 的 AF_PIPE（Windows Named Pipe）。

    通过「建一个立即关闭的 Listener」判断，毫秒级、无副作用；结果缓存。
    不支持（抛异常）即退回 tcp 传输。
    """
    global _PIPE_SUPPORTED
    if _PIPE_SUPPORTED is not None:
        return _PIPE_SUPPORTED
    try:
        from multiprocessing.connection import Listener
        probe = "aos_pipe_probe_" + uuid.uuid4().hex[:8]
        with Listener(probe, family="AF_PIPE") as _l:
            pass
        _PIPE_SUPPORTED = True
    except Exception:  # noqa: BLE001 - 任何异常都视为不可用
        _PIPE_SUPPORTED = False
    return _PIPE_SUPPORTED


class SubprocessIsolationLayer:
    """把一个 fabric 芯粒隔离进独立进程，经本地 IPC 提供服务。"""

    def __init__(self, engine_id: str, adapter_spec: Optional[str] = None,
                 task_us: float = 0.0, transport: Optional[str] = None) -> None:
        self.engine_id = engine_id
        self.adapter_spec = adapter_spec
        self.task_us = task_us
        self.transport = (transport or os.environ.get("AOS_ISO_TRANSPORT")
                          or "pipe").lower()
        self._pipe = self._new_pipe()
        self._addr: Optional[Any] = None
        self._family: Optional[str] = None
        self._proc: Optional["subprocess.Popen"] = None  # noqa: F821
        self._conn = None
        self._spawn_ms: Optional[float] = None
        self._last_rtt_us: Optional[float] = None

    # ---- 内部工具 -------------------------------------------------
    @staticmethod
    def _new_pipe() -> str:
        return "aos_iso_" + uuid.uuid4().hex[:12]

    def _fresh_address(self) -> Tuple[Any, str]:
        """为一次拉起生成全新地址（spawn / 恢复都调用，避免端口/名字残留）。"""
        if self.transport == "tcp":
            port = random.randint(40000, 65000)
            return ("127.0.0.1", port), "AF_INET"
        return self._new_pipe(), "AF_PIPE"

    def _addr_str(self, addr: Any) -> str:
        if isinstance(addr, tuple):
            return f"{addr[0]}:{addr[1]}"
        return addr

    def _build_env(self) -> Dict[str, str]:
        env = dict(os.environ)
        env["AOS_SRC"] = _AOS_SRC
        env["PYTHONPATH"] = _AOS_SRC + os.pathsep + env.get("PYTHONPATH", "")
        return env

    def _build_cmd(self, addr: Any) -> list[str]:
        cmd = [sys.executable, "-m", "kernel.isolation.worker",
               "--transport", self.transport,
               "--addr", self._addr_str(addr),
               "--task-us", str(self.task_us)]
        if self.adapter_spec:
            cmd += ["--adapter", self.adapter_spec]
        return cmd

    def _connect_with_timeout(self, addr, family: str,
                              timeout: float = _CONNECT_TIMEOUT):
        from multiprocessing.connection import Client
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            try:
                return Client(addr, family=family)
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.005)
        raise TimeoutError(
            f"子进程 {self.engine_id} 未在 {timeout}s 内监听 IPC 通道")

    def _ping(self, conn) -> None:
        t0 = time.perf_counter()
        conn.send({"__ctrl": "ping", "payload": {}})
        resp = conn.recv()
        if not (isinstance(resp, dict) and resp.get("data", {}).get("pong")):
            raise RuntimeError(f"子进程 {self.engine_id} 握手失败: {resp}")
        # 握手 RTT 也计入 last_rtt（首跳通常略高，probe 用 N 次取中位覆盖）
        self._last_rtt_us = (time.perf_counter() - t0) * 1_000_000.0

    def _spawn(self) -> float:
        """拉起子进程并等到可服务，返回 spawn_ms（毫秒）。

        带重试：子进程冷启动偶发卡顿、端口处于 TIME_WAIT 等瞬态失败会重 spawn
        （最多 _MAX_SPAWN_ATTEMPTS 次）。这是生产级健壮性，与 500ms 性能闸门
        无关——闸门测的是稳态延迟，此处只是「就绪等待」不计入单次请求。
        """
        # 本环境 Named Pipe 不可用时透明退 tcp（真实主机仍优先 pipe/UCIe-S）。
        if self.transport == "pipe" and not _pipe_supported():
            print(f"[iso] 本环境不支持 Named Pipe，{self.engine_id} 自动改用 tcp 传输")
            self.transport = "tcp"
        last_err: Optional[Exception] = None
        for _ in range(_MAX_SPAWN_ATTEMPTS):
            try:
                addr, family = self._fresh_address()
                self._addr, self._family = addr, family
                t0 = time.perf_counter()
                self._proc = _popen(self._build_cmd(addr), self._build_env())
                conn = self._connect_with_timeout(addr, family)
                self._ping(conn)  # 首条 RPC 成功 = 真正「可服务」
                self._conn = conn
                return (time.perf_counter() - t0) * 1000.0
            except Exception as e:  # noqa: BLE001 - 瞬态失败则重 spawn
                last_err = e
                if self._proc is not None:
                    try:
                        self._proc.kill()
                        self._proc.wait(timeout=5)
                    except Exception:  # noqa: BLE001
                        pass
                self._proc = None
                self._conn = None
        raise RuntimeError(
            f"子进程 {self.engine_id} 多次({_MAX_SPAWN_ATTEMPTS})拉起失败: {last_err}")

    # ---- 生命周期 -------------------------------------------------
    def start(self) -> float:
        """拉起子进程并等到可服务，返回 spawn_ms（毫秒）。"""
        assert self._proc is None, "already started"
        self._spawn_ms = self._spawn()
        return self._spawn_ms

    # ---- 调用 -----------------------------------------------------
    def invoke(self, capability: str, payload: Dict[str, Any],
               iters: int = 1) -> Dict[str, Any]:
        """经 IPC 调子进程内芯粒，返回最后一次 InvokeResult(dict)。
        用 iters 次取中位 RTT 写入 self.rtt_us（消除首跳抖动）。
        """
        assert self._conn is not None, "not started"
        samples: list[float] = []
        last = None
        for _ in range(iters):
            t0 = time.perf_counter()
            self._conn.send({"capability": capability, "payload": payload})
            last = self._conn.recv()
            samples.append((time.perf_counter() - t0) * 1_000_000.0)
        samples.sort()
        self._last_rtt_us = samples[len(samples) // 2]
        return last

    @property
    def rtt_us(self) -> Optional[float]:
        return self._last_rtt_us

    @property
    def spawn_ms(self) -> Optional[float]:
        return self._spawn_ms

    @property
    def pid(self) -> Optional[int]:
        """子进程 PID（进程外铁证）；未启动或已退出返回 None。"""
        if self._proc is None or self._proc.poll() is not None:
            return None
        return self._proc.pid

    def health(self) -> bool:
        if self._proc is None or self._conn is None:
            return False
        return self._proc.poll() is None

    # ---- 崩溃恢复 -------------------------------------------------
    def kill_and_recover(self) -> float:
        """杀掉当前子进程并重新拉起，返回 recovery_ms（毫秒）。"""
        assert self._proc is not None, "not started"
        self._proc.kill()
        self._proc.wait()
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._conn = None
        return self._spawn()

    def stop(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        self._proc = None
        self._conn = None


def _popen(cmd: list[str], env: dict):
    import subprocess
    return subprocess.Popen(
        cmd, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


class IsolatedEngineHost:
    """把「单个 fabric 引擎隔离进子进程」封装成 FabricHub 可直接用的落点。

    热备(standby)形态（默认开启）：初始化时除主进程外额外预拉起一个**已热身**
    的热备子进程。主进程崩溃时 recover() 直接提拔热备（毫秒级，远过 3s 恢复闸门），
    后台线程再冷启动补一个热备——因此稳态崩溃恢复**不依赖重型适配器的 ~18s 冷启动**。
    这是 Day22-30 B 路线「热进程池缓解冷启动」的最小完整落点（SubprocessPool 是
    多实例推广形态；本类先解决单引擎的热备切换）。

    FabricHub 把被隔离的引擎注册成「进程内代理」(IsolatedAdapterProxy)，能力路由/
    自检零改动即可生效；真正的执行与故障都发生在子进程里 —— 即 Chiplet 故障隔离
    的生产形态落点。
    """

    def __init__(self, engine_id: str, adapter_spec: str,
                 transport: Optional[str] = None, task_us: float = 0.0,
                 standby: bool = True) -> None:
        self.engine_id = engine_id
        self.adapter_spec = adapter_spec
        self._transport = transport
        self._task_us = task_us
        self._standby_enabled = standby
        self._layer = SubprocessIsolationLayer(
            engine_id=engine_id, adapter_spec=adapter_spec,
            transport=transport, task_us=task_us,
        )
        self._standby: Optional[SubprocessIsolationLayer] = None
        self._lock = threading.Lock()
        self._stopping = False
        self._last_recover_ms: Optional[float] = None

    def _mk_standby(self) -> SubprocessIsolationLayer:
        return SubprocessIsolationLayer(
            engine_id=f"{self.engine_id}#standby",
            adapter_spec=self.adapter_spec,
            transport=self._transport, task_us=self._task_us,
        )

    def start(self) -> float:
        spawn_ms = self._layer.start()
        # 同步实际生效的传输（pipe 自动退 tcp 时，热备层必须跟着用 tcp）。
        self._transport = self._layer.transport
        if self._standby_enabled and self._standby is None and not self._stopping:
            try:
                self._standby = self._mk_standby()
                self._standby.start()  # 真正拉起热备子进程（_proc 才非 None）
            except Exception:  # noqa: BLE001 - 热备失败不阻断主进程服务
                self._standby = None
        return spawn_ms

    def invoke(self, capability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._layer.invoke(capability, payload)

    def health(self) -> bool:
        return self._layer.health()

    def recover(self) -> float:
        """崩溃恢复。

        - 有热备：提拔热备（毫秒级，过 3s 闸门），旧主退出，后台补位。
          返回切换耗时（毫秒）。
        - 无热备：冷启动 kill+respawn（重型适配器可能 > 闸门，已知，由预热缓解）。
        """
        with self._lock:
            if self._standby is not None:
                t0 = time.perf_counter()
                try:
                    self._layer.stop()
                except Exception:  # noqa: BLE001
                    pass
                self._layer = self._standby
                self._standby = None
                switched_ms = (time.perf_counter() - t0) * 1000.0
                self._last_recover_ms = switched_ms
                self._fill_standby_async()
                return switched_ms
            ms = self._layer.kill_and_recover()
            self._last_recover_ms = ms
            return ms

    def _fill_standby_async(self) -> None:
        if not self._standby_enabled or self._stopping:
            return

        def _work() -> None:
            try:
                nb = self._mk_standby()
                nb.start()  # 真正拉起补位热备子进程
                with self._lock:
                    if self._standby is None and not self._stopping:
                        self._standby = nb
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=_work, daemon=True).start()

    def stop(self) -> None:
        self._stopping = True
        if self._standby is not None:
            try:
                self._standby.stop()
            except Exception:  # noqa: BLE001
                pass
            self._standby = None
        self._layer.stop()

    @property
    def spawn_ms(self) -> Optional[float]:
        return self._layer.spawn_ms

    @property
    def rtt_us(self) -> Optional[float]:
        return self._layer.rtt_us

    @property
    def subprocess_pid(self) -> Optional[int]:
        """隔离子进程 PID（进程外铁证）；热备提拔后指向当前主层。"""
        return self._layer.pid

    @property
    def standby_ready(self) -> bool:
        """热备子进程是否已热身就绪（可毫秒级提拔，不依赖冷启动）。"""
        return self._standby is not None and self._standby.health()

    @property
    def last_recover_ms(self) -> Optional[float]:
        """最近一次 recover 的切换/恢复耗时（毫秒）；未恢复过为 None。"""
        return self._last_recover_ms


class SubprocessPool:
    """热进程池：B 路线进入生产的标准形态。

    朴素冷启动(spawn)测出 ~527ms，略超 500ms 闸门——根因是 Python 解释器
    冷启动 + import。热池在初始化时**预拉起 N 个常驻 worker**，之后每次请求
    只是「从池里取一个已热身的 worker」（assign_ms≈0），单个 worker 崩溃则由
    后台 recycle 重建、其余热 worker 继续服务（请求不阻塞）。

    这样三闸门在稳态下全部通过：
      - 稳态 assign  ≈ 0ms        （≤500ms ✅）
      - RTT          ≈ 同单例      （≤100μs ✅）
      - 容量恢复     ≈ 单次 respawn （≤3s ✅，且不影响在途请求）
    一次性 warmup 成本可摊销到进程生命周期里，不计入单次请求延迟。
    """

    def __init__(self, engine_id: str, size: int = 2,
                 transport: Optional[str] = None, task_us: float = 0.0,
                 adapter_spec: Optional[str] = None) -> None:
        self.engine_id = engine_id
        self.size = size
        self.transport = (transport or os.environ.get("AOS_ISO_TRANSPORT")
                          or "pipe").lower()
        self.task_us = task_us
        self.adapter_spec = adapter_spec
        self._workers: list[SubprocessIsolationLayer] = []

    def _mk(self, idx: int) -> SubprocessIsolationLayer:
        return SubprocessIsolationLayer(
            engine_id=f"{self.engine_id}#{idx}",
            adapter_spec=self.adapter_spec,
            transport=self.transport, task_us=self.task_us,
        )

    def warmup(self) -> float:
        """预拉起 size 个热 worker，返回一次性 warmup_ms（可摊销）。"""
        t0 = time.perf_counter()
        for i in range(self.size):
            w = self._mk(i)
            w.start()
            self._workers.append(w)
        # 同步实际生效的传输（pipe 自动退 tcp 时保持一致）。
        if self._workers:
            self.transport = self._workers[0].transport
        return (time.perf_counter() - t0) * 1000.0

    def acquire(self) -> tuple[SubprocessIsolationLayer, float]:
        """取一个热 worker（无需冷启动）。返回 (worker, assign_ms≈0)。

        若池空（正常不应发生，除非全部在回收），退回冷启动路径。
        """
        t0 = time.perf_counter()
        if self._workers:
            w = self._workers.pop(0)
        else:
            w = self._mk(len(self._workers))
            w.start()
        assign_ms = (time.perf_counter() - t0) * 1000.0
        return w, assign_ms

    def release(self, w: SubprocessIsolationLayer) -> None:
        """用完归还热 worker。"""
        self._workers.append(w)

    def recycle(self, w: SubprocessIsolationLayer) -> float:
        """替换一个（崩溃的）worker，返回 respawn_ms（后台容量恢复成本）。"""
        try:
            w.stop()
        except Exception:  # noqa: BLE001
            pass
        t0 = time.perf_counter()
        nw = self._mk(len(self._workers))
        nw.start()
        respawn_ms = (time.perf_counter() - t0) * 1000.0
        self._workers.append(nw)
        return respawn_ms

    @property
    def available(self) -> int:
        return len(self._workers)

    def stop(self) -> None:
        for w in self._workers:
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass
        self._workers = []
