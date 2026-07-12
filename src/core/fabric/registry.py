"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import Capability


# 供给方偏好（越小越优先）。默认「云端优先、本地兜底」，把 AOS 的
# 「万物为我所用 / 端云合作 / 云端用不了就本地」从口号变成路由层的运行时节点击穿：
# 云端供给方可达时先用（质量/速度），不可达/失败时自动降级到本地供给方。
# 想调顺序（如默认本地优先）改这里即可，不动任何适配器代码——这就是「不绑定」。
PROVIDER_PREFERENCE: dict[str, int] = {
    "openclaw": 10,    # 网关背后云 LLM，优先
    "agnes": 10,       # 云端多模态平面
    "ag2": 20,         # 规划/推理（可走云或本地）
    "litellm": 20,     # 推理网关（云模型优先）
    "search": 30,      # 搜索（含 anysearch 云 + 国内 HTML 兜底）
    "browseruse": 40,
    "langfuse": 50,
    "mem0": 90,        # 记忆默认本地零成本兜底（AOS_MEM0_LOCAL=1）
}
_DEFAULT_PREF = 50


def _pref(engine_id: str) -> int:
    return PROVIDER_PREFERENCE.get(engine_id, _DEFAULT_PREF)


class FabricRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, BaseAgentAdapter] = {}

    def register(self, adapter: BaseAgentAdapter) -> None:
        self._adapters[adapter.engine_id] = adapter

    @staticmethod
    def _cap_to_str(cap) -> str:
        """能力统一成字符串：兼容 Capability 枚举(API 内部)与字符串(API 入参)。"""
        return cap.value if hasattr(cap, "value") else str(cap)

    def providers_for(self, cap: Capability) -> list[BaseAgentAdapter]:
        cap_str = self._cap_to_str(cap)
        live = [
            a
            for a in self._adapters.values()
            if cap_str in {self._cap_to_str(c) for c in a.advertise_capabilities()}
            and a.health()
        ]
        # 按供给方偏好排序：云端优先、本地兜底（体现端云合作）。
        return sorted(live, key=lambda a: _pref(a.engine_id))

    def route(self, req: InvokeRequest) -> InvokeResult:
        """按能力路由，并在 live 供给方之间做**运行时故障转移**：

        - 依偏好排序（云端优先→本地兜底）逐个尝试；
        - 任一供给方 `ok=False` 或抛异常，自动跳到下一个 live 供给方；
        - 全部失败才返回合并错误。

        这就是「云端用不了就本地 / 万物为我所用」的真实执行路径——
        调用方永远不感知背后是云还是端，AOS 统一协商。
        """
        providers = self.providers_for(req.capability)
        if not providers:
            cap_str = self._cap_to_str(req.capability)
            return InvokeResult(ok=False, error=f"no live provider for {cap_str}")
        last_res: InvokeResult | None = None
        attempts: list[str] = []
        for p in providers:
            try:
                res = p.invoke(req)
            except Exception as e:  # noqa: BLE001 - 单个供给方崩溃不阻断协商
                attempts.append(f"{p.engine_id} raised: {e!r}")
                continue
            if res.ok:
                return res
            attempts.append(f"{p.engine_id}: {res.error}")
            last_res = res
        # 全部失败：返回最后一个供给方的真实结果（保留其 data，如编排 trace/
        # ok_steps），错误附注「已协商 N 个供给方」以体现端云合作耗尽，而非合成
        # 一个 data=None 的空结果把下游有用的失败上下文吞掉。
        if last_res is not None:
            return InvokeResult(
                ok=False,
                data=last_res.data,
                error=f"all providers failed [{req.capability.value}] "
                      f"after {len(attempts)} attempt(s): " + " | ".join(attempts),
            )
        return InvokeResult(
            ok=False,
            error=f"all providers raised [{req.capability.value}]: " + " | ".join(attempts),
        )

    def snapshot(self) -> dict[str, list[str]]:
        return {
            eid: [c.value for c in a.advertise_capabilities()]
            for eid, a in self._adapters.items()
        }

    def get(self, engine_id: str) -> "BaseAgentAdapter | None":
        """按 engine_id 取已注册适配器（进程内）。

        隔离引擎(B 路线子进程)由 FabricHub 单独持有，不在此返回。
        """
        return self._adapters.get(engine_id)
