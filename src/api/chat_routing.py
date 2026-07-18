"""Chat 后端路由决策（单基座第一性）。

把 /api/chat 的后端选择从 main.py 内联逻辑抽出来，集中成可单测的纯函数。

设计原则（对应 AOS 九大理念）：
- 单基座第一性：默认主后端 = FabricHub（目标「唯一运行时」），不再把 brain.py
  当默认兜底。
- 诚实+量化：每个后端失败都诚实回退到下一后端，绝不伪造响应（理念6/9）。
- 故障隔离：后端链任一节点抛错都不阻断整条链路，仅降级到下一节点。

环境变量（改 env 无需重启即生效）：
- AOS_CHAT_BACKEND : fabric(默认) | kernel | brain
    - fabric：经 FabricHub.chat() 单一运行时（inference.llm 芯粒，云端优先→本地兜底）
    - kernel：经 v1.0 内核（AOSKernel → mistralrs 本地推理）
    - brain ：legacy core/brain.py（UnifiedBrain），已废弃，仅作显式选择
- AOS_BRAIN_FALLBACK : "1" 时把 brain.py 加入兜底链末端（opt-in 兜底）
"""
import os
from typing import List

BACKEND_FABRIC = "fabric"
BACKEND_KERNEL = "kernel"
BACKEND_BRAIN = "brain"

DEFAULT_BACKEND = BACKEND_FABRIC

BRAIN_DEPRECATION_MSG = (
    "DEPRECATED: /api/chat served by legacy core/brain.py (UnifiedBrain). "
    "brain.py is being retired as the default chat runtime; /api/chat now "
    "defaults to FabricHub. Set AOS_CHAT_BACKEND=brain or AOS_BRAIN_FALLBACK=1 "
    "to keep using it. New chat code should route through FabricHub."
)


def select_chat_backends() -> List[str]:
    """依据 env 返回 /api/chat 的有序后端链（主→次→...）。

    返回列表的语义：依次尝试，前一后端抛错则降级到下一后端；全部抛错则
    /api/chat 诚实返回 503（不伪造响应）。

    - 默认 [fabric, kernel]：单基座第一性，FabricHub 为主，内核为次。
    - AOS_BRAIN_FALLBACK=1 时链末端追加 brain（opt-in 兜底）。
    - AOS_CHAT_BACKEND=kernel：链为 [kernel]（+brain 若 opt-in）。
    - AOS_CHAT_BACKEND=brain ：链为 [brain]（显式 legacy，仍打废弃标记）。
    """
    backend = (os.environ.get("AOS_CHAT_BACKEND") or DEFAULT_BACKEND).lower()
    brain_fb = os.environ.get("AOS_BRAIN_FALLBACK", "0") == "1"

    if backend == BACKEND_BRAIN:
        # 显式选择 legacy 路径（仍走废弃标记）
        return [BACKEND_BRAIN]
    if backend == BACKEND_KERNEL:
        chain = [BACKEND_KERNEL]
        if brain_fb:
            chain.append(BACKEND_BRAIN)
        return chain
    # fabric（默认）
    chain = [BACKEND_FABRIC, BACKEND_KERNEL]
    if brain_fb:
        chain.append(BACKEND_BRAIN)
    return chain
