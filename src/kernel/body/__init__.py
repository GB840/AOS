"""L1 肉体层 —— 生命体OS 的物理承载与设备抽象（白皮书 L1）。

子模块：
- hal        L1G 硬件抽象层统一指令集（异构算力/传感器/执行器统一指令封装）
- phy_bus    L1H Phy-Bus 物理适配总线（设备↔内核的带安全联锁的消息总线）

诚实度：本层为 ① 代码就绪 + ② 单元验证（tests/test_body_hal.py、test_phy_bus.py）；
真实硬件（GPU/NPU/机械臂/眼镜）驱动为 ③ 待验，当前仅提供 dry-run 驱动与真实错误回传。
"""

from .hal import (
    HAL,
    Instruction,
    InstructionResult,
    DeviceProfile,
    DryRunDriver,
    UnsupportedInstruction,
)
from .phy_bus import PhyBus, PhyMessage, Interlock, InterlockDenied

__all__ = [
    "HAL",
    "Instruction",
    "InstructionResult",
    "DeviceProfile",
    "DryRunDriver",
    "UnsupportedInstruction",
    "PhyBus",
    "PhyMessage",
    "Interlock",
    "InterlockDenied",
]
