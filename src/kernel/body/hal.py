"""L1G 硬件抽象层统一指令集 —— 完全自研核心（生命体OS 白皮书 L1G）。

目的：让上层（L2 心智 / L6 交互闭环）用**同一套指令**驱动异构物理载体，
不为任何一种硬件写死代码（对应宪法理念 4「万物为我所用，不为任何一物所绑定」）。

统一指令集（8 条原语，故意保持极小）：
    compute  在算力单元上跑一次计算（CPU/GPU/NPU）
    sense    读一次传感器（摄像头/麦克风/IMU/光感）
    actuate  驱动一次执行器（电机/震动/灯）
    render   输出到显示/音频设备
    query    查询设备状态（电量/温度/占用）
    reset    复位设备
    sleep    设备进入低功耗
    wake     唤醒设备

设计纪律：
1. 指令是**数据**（dataclass），不是方法名字符串拼接——可序列化、可审计、可跨进程。
2. 驱动只声明「我支持哪些 op」，HAL 按能力路由（宪法理念 5「能力即路由」）。
3. 失败**如实返回** exit_code/stderr，绝不伪造成功（宪法理念 6「诚实比聪明重要」）。
4. 无硬件环境下 DryRunDriver 保证链路可测，但结果显式标记 dry_run=True，不冒充真跑。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional

# ---------------------------------------------------------------- 指令集常量

OPS: tuple[str, ...] = (
    "compute", "sense", "actuate", "render", "query", "reset", "sleep", "wake",
)

# 危险 op：会对物理世界产生不可逆影响，必须经 Phy-Bus 安全联锁
DANGEROUS_OPS: frozenset[str] = frozenset({"actuate", "reset"})


class UnsupportedInstruction(RuntimeError):
    """没有任何已注册驱动能承接该指令。"""


@dataclass(frozen=True)
class Instruction:
    """统一指令封装：可序列化、可审计。"""

    op: str
    target: str = "auto"                 # 设备名；auto = 由 HAL 按能力挑
    args: Dict[str, Any] = field(default_factory=dict)
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if self.op not in OPS:
            raise ValueError(f"未知指令 op={self.op!r}，合法集合={OPS}")

    @property
    def dangerous(self) -> bool:
        return self.op in DANGEROUS_OPS

    def to_dict(self) -> dict:
        return {"op": self.op, "target": self.target,
                "args": dict(self.args), "timeout_s": self.timeout_s}


@dataclass
class InstructionResult:
    """执行结果：带真实退出码与耗时，供上层做量化置信判断。"""

    ok: bool
    op: str
    device: str
    output: Any = None
    error: str = ""
    exit_code: int = 0
    elapsed_ms: float = 0.0
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok, "op": self.op, "device": self.device,
            "output": self.output, "error": self.error,
            "exit_code": self.exit_code,
            "elapsed_ms": round(self.elapsed_ms, 3),
            "dry_run": self.dry_run,
        }


@dataclass
class DeviceProfile:
    """设备画像：驱动向 HAL 声明的能力与物理约束。"""

    name: str
    kind: str                              # cpu/gpu/npu/sensor/actuator/display/audio
    ops: frozenset[str]                    # 支持的指令
    max_power_w: float = 0.0               # 峰值功耗（用于 L2D 资源自治）
    latency_ms: float = 1.0                # 典型时延（用于路由择优）
    healthy: bool = True

    def supports(self, op: str) -> bool:
        return self.healthy and op in self.ops


class Driver:
    """驱动基类：实现 profile() + execute() 即可被 HAL 纳管。"""

    def profile(self) -> DeviceProfile:      # pragma: no cover - 抽象
        raise NotImplementedError

    def execute(self, instr: Instruction) -> InstructionResult:  # pragma: no cover
        raise NotImplementedError


class DryRunDriver(Driver):
    """无硬件环境下的可测驱动：全 op 支持，结果显式标 dry_run=True。"""

    def __init__(self, name: str = "dryrun0", kind: str = "cpu",
                 ops: Optional[Iterable[str]] = None, latency_ms: float = 0.5):
        self._profile = DeviceProfile(
            name=name, kind=kind,
            ops=frozenset(ops) if ops else frozenset(OPS),
            latency_ms=latency_ms,
        )

    def profile(self) -> DeviceProfile:
        return self._profile

    def execute(self, instr: Instruction) -> InstructionResult:
        t0 = time.perf_counter()
        return InstructionResult(
            ok=True, op=instr.op, device=self._profile.name,
            output={"echo": instr.args}, dry_run=True,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )


class CallableDriver(Driver):
    """把普通函数包成驱动，便于把 AOS 已有芯粒接进 HAL 而不改它们。"""

    def __init__(self, profile: DeviceProfile, fn: Callable[[Instruction], Any]):
        self._profile = profile
        self._fn = fn

    def profile(self) -> DeviceProfile:
        return self._profile

    def execute(self, instr: Instruction) -> InstructionResult:
        t0 = time.perf_counter()
        try:
            out = self._fn(instr)
            return InstructionResult(
                ok=True, op=instr.op, device=self._profile.name, output=out,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as exc:  # 如实回传，不吞异常
            return InstructionResult(
                ok=False, op=instr.op, device=self._profile.name,
                error=f"{type(exc).__name__}: {exc}", exit_code=1,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )


class HAL:
    """硬件抽象层：注册驱动 → 按能力路由 → 统一执行 → 真实结果。"""

    def __init__(self) -> None:
        self._drivers: Dict[str, Driver] = {}
        self._trace: List[dict] = []

    # ---------------------------------------------------------- 注册 / 发现
    def register(self, driver: Driver) -> str:
        p = driver.profile()
        self._drivers[p.name] = driver
        return p.name

    def unregister(self, name: str) -> bool:
        return self._drivers.pop(name, None) is not None

    def devices(self) -> List[DeviceProfile]:
        return [d.profile() for d in self._drivers.values()]

    def capabilities(self) -> Dict[str, List[str]]:
        """op -> 能承接它的设备名列表（能力即路由的可视化）。"""
        cap: Dict[str, List[str]] = {op: [] for op in OPS}
        for d in self._drivers.values():
            p = d.profile()
            for op in p.ops:
                if p.healthy:
                    cap[op].append(p.name)
        return cap

    # ---------------------------------------------------------------- 路由
    def route(self, instr: Instruction) -> Optional[Driver]:
        if instr.target != "auto":
            d = self._drivers.get(instr.target)
            return d if d and d.profile().supports(instr.op) else None
        cands = [d for d in self._drivers.values() if d.profile().supports(instr.op)]
        if not cands:
            return None
        # 择优：时延最小者优先（真实硬件驱动优先于 dry-run，因其 latency 通常更真实）
        return min(cands, key=lambda d: d.profile().latency_ms)

    # ---------------------------------------------------------------- 执行
    def execute(self, instr: Instruction) -> InstructionResult:
        driver = self.route(instr)
        if driver is None:
            raise UnsupportedInstruction(
                f"无驱动可承接 op={instr.op} target={instr.target}；"
                f"当前设备={[p.name for p in self.devices()]}"
            )
        res = driver.execute(instr)
        self._trace.append({"instr": instr.to_dict(), "result": res.to_dict()})
        return res

    def try_execute(self, instr: Instruction) -> InstructionResult:
        """不抛异常版：无驱动时返回 ok=False 的真实错误结果。"""
        try:
            return self.execute(instr)
        except UnsupportedInstruction as exc:
            return InstructionResult(ok=False, op=instr.op, device="-",
                                     error=str(exc), exit_code=127)

    @property
    def trace(self) -> List[dict]:
        return list(self._trace)


__all__ = [
    "OPS", "DANGEROUS_OPS", "Instruction", "InstructionResult", "DeviceProfile",
    "Driver", "DryRunDriver", "CallableDriver", "HAL", "UnsupportedInstruction",
]
