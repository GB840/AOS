"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import (
    Capability,
    TIER_HIGH,
    TIER_MEDIUM,
    TIER_LOW,
    TIER_AUTO,
    TIER_RANK,
    ENGINE_TIER,
)


# 供给方偏好（同档内的二级排序键，越小越优先）。默认「云端优先、本地兜底」，
# 把 AOS 的「万物为我所用 / 端云合作 / 云端用不了就本地」从口号变成路由层
# 运行时节点击穿：档位相同时，云端供给方先试（质量/速度），失败自动降级本地。
# 想调顺序（如默认本地优先）改这里即可，不动任何适配器代码——这就是「不绑定」。
# 注意：偏好只是「同档内」的次级排序；档位(tier)才是第一维度（见 ROUTE_TIER）。
PROVIDER_PREFERENCE: dict[str, int] = {
    "openclaw": 10,    # 网关背后云 LLM，优先
    "agnes": 10,       # 云端多模态平面
    "ag2": 20,         # 规划/推理（可走云或本地）
    "litellm": 20,     # 推理网关（云模型优先）
    "search": 30,      # 搜索（含 anysearch 云 + 国内 HTML 兜底）
    "web-fetch": 30,   # URL 内容抓取（与搜索同层级）
    "browseruse": 40,
    "code-exec": 40,   # 本地代码执行（subprocess 隔离，零依赖）
    "file-io": 40,     # 文件读写（workspace 内）
    "langfuse": 50,
    "mem0": 90,        # 记忆默认本地零成本兜底（AOS_MEM0_LOCAL=1）
}
_DEFAULT_PREF = 50

# 全局默认档位策略：动态路由的第一维度。
# - auto(默认)：运行时从最高档向低档级联（高→中→低），即「云端用不了就本地 /
#   端云合作」的真实执行路径——优先用最佳可达档，逐级兜底，绝不写死单档。
# - high/medium/low：把起始(最高)档固定为该档，仍向下级联到更低档。
ROUTE_TIER = TIER_AUTO

# 路由策略（档位内的二级排序）：把 Auriko 的成本套利内核原生借进 AOS。
# - preference：默认，按 PROVIDER_PREFERENCE 排序（同档内云端优先→本地兜底）。
# - cost：成本优先（provider_cost 越小越先，单位相对分）。
# - latency：延迟优先（provider_latency 越小越先）。
# - quality：质量优先（provider_quality 越大越先）。
ROUTE_STRATEGY = "preference"
PROVIDER_COST: dict[str, float] = {}       # engine_id -> 相对成本（低优先）
PROVIDER_LATENCY: dict[str, float] = {}   # engine_id -> 相对延迟（低优先）
PROVIDER_QUALITY: dict[str, float] = {}   # engine_id -> 质量分（高优先）


def _pref(engine_id: str) -> int:
    return PROVIDER_PREFERENCE.get(engine_id, _DEFAULT_PREF)


class FabricRegistry:
    def __init__(
        self,
        strategy: str | None = None,
        tier: str | None = None,
        provider_cost: dict[str, float] | None = None,
        provider_latency: dict[str, float] | None = None,
        provider_quality: dict[str, float] | None = None,
    ) -> None:
        self._adapters: dict[str, BaseAgentAdapter] = {}
        # 实例级策略，避免改全局影响其它枢纽；默认读模块级 ROUTE_STRATEGY。
        self.strategy = strategy or ROUTE_STRATEGY
        # 实例级默认档位（第一维度）；默认读模块级 ROUTE_TIER（auto=级联）。
        self.tier = tier or ROUTE_TIER
        self._cost = provider_cost if provider_cost is not None else dict(PROVIDER_COST)
        self._latency = provider_latency if provider_latency is not None else dict(PROVIDER_LATENCY)
        self._quality = provider_quality if provider_quality is not None else dict(PROVIDER_QUALITY)

    def register(self, adapter: BaseAgentAdapter) -> None:
        self._adapters[adapter.engine_id] = adapter

    @staticmethod
    def _cap_to_str(cap) -> str:
        """能力统一成字符串：兼容 Capability 枚举(API 内部)与字符串(API 入参)。"""
        return cap.value if hasattr(cap, "value") else str(cap)

    def _sort_key(self, a: BaseAgentAdapter) -> float:
        """依当前策略对 live 供给方排序（返回越小越优先）。"""
        eid = a.engine_id
        if self.strategy == "cost":
            # 成本套利：最便宜的供给方排最前（Auriko 内核）。
            return self._cost.get(eid, 50.0)
        if self.strategy == "latency":
            return self._latency.get(eid, 50.0)
        if self.strategy == "quality":
            # 质量优先：分数越大越靠前 → 取负。
            return -self._quality.get(eid, 50.0)
        return float(_pref(eid))

    def _tier_of(self, a: BaseAgentAdapter) -> str:
        """取引擎实际档位（高/中/低），非法值回落中档。"""
        t = a.tier()
        return t if t in TIER_RANK else TIER_MEDIUM

    def providers_for(self, cap: Capability, tier: str | None = None) -> list[BaseAgentAdapter]:
        """返回某能力的 live 供给方，按**档位优先 + 策略次级**排序。

        档位维度（动态路由第一维度）：
        - `tier` = 起始(最高)档；从该档向低档级联（高→中→低）。
          auto/high 从高档起；medium 从中档起；low 仅低档。
        - 这就是「云端用不了就本地 / 端云合作」的真实执行路径：
          优先用最佳可达档，逐级兜底，绝不写死单档。

        同档内再依 ROUTE_STRATEGY（preference/cost/latency/quality）排序。
        route() 仍会在排序后的供给方之间做运行时故障转移（Auriko fallback 语义）。
        """
        cap_str = self._cap_to_str(cap)
        live = [
            a
            for a in self._adapters.values()
            if cap_str in {self._cap_to_str(c) for c in a.advertise_capabilities()}
            and a.health()
        ]
        start = TIER_RANK.get(tier or self.tier, TIER_RANK[TIER_HIGH])
        # 仅保留档位 >= 起始档的供给方（实现「向低档级联」）
        cands = [
            a for a in live
            if TIER_RANK.get(self._tier_of(a), TIER_RANK[TIER_MEDIUM]) >= start
        ]
        # 先按档位(高->低)，同档内按策略排序
        cands.sort(key=lambda a: (
            TIER_RANK.get(self._tier_of(a), TIER_RANK[TIER_MEDIUM]),
            self._sort_key(a),
        ))
        return cands

    def tiers_for(self, cap: Capability) -> list[str]:
        """某能力当前 live 可达的档位（高/中/低），即「能力分级」运行时视图。

        供调用方/UI 展示该能力可被哪些档位满足，或决定请求哪个档位。
        """
        ranks = {
            TIER_RANK.get(self._tier_of(a), TIER_RANK[TIER_MEDIUM])
            for a in self.providers_for(cap)
        }
        return [t for t in (TIER_HIGH, TIER_MEDIUM, TIER_LOW) if TIER_RANK.get(t) in ranks]

    def route(self, req: InvokeRequest) -> InvokeResult:
        """按能力路由，并在 live 供给方之间做**运行时故障转移**：

        - 档位优先：优先用最高可达档（auto 从高档起，向低档级联）；
        - 同档内依偏好/策略排序（云端优先→本地兜底）逐个尝试；
        - 任一供给方 `ok=False` 或抛异常，自动跳到下一个 live 供给方；
        - 全部失败才返回合并错误。

        这就是「云端用不了就本地 / 万物为我所用」的真实执行路径——
        调用方永远不感知背后是云还是端、用的是什么档，AOS 统一协商。
        请求可在 `req.tier` / `payload['tier']` 指定起始档（高/中/低），
        缺省用本注册表默认档位（默认 auto=级联）。
        """
        req_tier = getattr(req, "tier", None) or (req.payload or {}).get("tier")
        providers = self.providers_for(req.capability, req_tier)
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
            eid: [self._cap_to_str(c) for c in a.advertise_capabilities()]
            for eid, a in self._adapters.items()
        }

    def get(self, engine_id: str) -> "BaseAgentAdapter | None":
        """按 engine_id 取已注册适配器（进程内）。

        隔离引擎(B 路线子进程)由 FabricHub 单独持有，不在此返回。
        """
        return self._adapters.get(engine_id)
