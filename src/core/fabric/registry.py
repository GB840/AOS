"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

import time

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import (
    Capability,
    TIER_HIGH,
    TIER_MEDIUM,
    TIER_LOW,
    TIER_AUTO,
    TIER_RANK,
)
from .route_outcome_store import RouteOutcomeStore
from .route_predictor import RoutePredictor


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
        predictor: "RoutePredictor | None" = None,
        outcome_store: "RouteOutcomeStore | None" = None,
        predictor_path: str | None = None,
        retrain_gap: int = 8,
    ) -> None:
        self._adapters: dict[str, BaseAgentAdapter] = {}
        # 实例级策略，避免改全局影响其它枢纽；默认读模块级 ROUTE_STRATEGY。
        self.strategy = strategy or ROUTE_STRATEGY
        # 实例级默认档位（第一维度）；默认读模块级 ROUTE_TIER（auto=级联）。
        self.tier = tier or ROUTE_TIER
        self._cost = provider_cost if provider_cost is not None else dict(PROVIDER_COST)
        self._latency = provider_latency if provider_latency is not None else dict(PROVIDER_LATENCY)
        self._quality = provider_quality if provider_quality is not None else dict(PROVIDER_QUALITY)
        # 路由预测器（白盒进化）：默认不注入 → 回落静态策略，现有行为完全不变。
        # 仅当显式 strategy="learned" 且 predictor 已训练时，才用预测分排序。
        self.predictor = predictor
        self.outcome_store = outcome_store
        # 预测模型持久化路径：训练后落盘，重启自动加载（越用越准且可复现）。
        self.predictor_path = predictor_path
        # 距上次训练再积累 retrain_gap 条新样本才重训，避免每条都重训的开销。
        self._retrain_gap = retrain_gap
        # 已用于训练的样本数；加载已训练模型时对齐到当前落盘数，避免启动即重训。
        self._last_trained_count = (
            outcome_store.count() if (predictor is not None and predictor.trained
                                      and outcome_store is not None) else 0
        )

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

    def _intra_tier_key(self, a: BaseAgentAdapter, cap_str: str, tier: str | None = None) -> float:
        """同档内的次级排序键。

        learned 策略且 predictor 已训练时，用预测成功概率（高分优先→取负）；
        否则回落原静态策略。档位维度由调用方（providers_for）保证优先，
        并与 record_outcome 落盘时使用的档位保持一致（同为 eff_tier）。
        """
        if (self.strategy == "learned" and self.predictor is not None
                and self.predictor.trained):
            return -self.predictor.predict(cap_str, a.engine_id, tier or self.tier)
        return self._sort_key(a)

    def _record_outcome(self, cap_str: str, engine: str, tier, ok: bool,
                        latency_ms: float, error=None) -> None:
        """把一次路由尝试的真实结果落盘（供 predictor 学习）。无 store 则跳过。"""
        if self.outcome_store is not None:
            self.outcome_store.record(cap_str, engine, tier or "", ok, latency_ms, error)

    def maybe_retrain(self) -> None:
        """白盒进化闭环：learned 且数据够、且距上次训练又积累够 retrain_gap 条时，
        从全部落盘结果重训（越用越准），并把模型持久化到 predictor_path。

        闸门：
        - 必须 strategy=learned 且注入了 predictor + outcome_store；
        - 样本不足最小阈值（RouteOutcomeStore._MIN_SAMPLES）不训；
        - 已训练后，仅当新增样本达到 retrain_gap 才重训，控制开销。
        """
        if (self.strategy != "learned" or self.predictor is None
                or self.outcome_store is None):
            return
        cnt = self.outcome_store.count()
        if not self.outcome_store.trainable():
            return
        if cnt < self._last_trained_count + self._retrain_gap:
            return
        records = self.outcome_store.load()
        if not records:
            return
        self.predictor.fit(records)
        self._last_trained_count = cnt
        if self.predictor_path:
            try:
                self.predictor.save(self.predictor_path)
            except Exception:  # noqa: BLE001 - 持久化失败不致命，内存模型仍可用
                pass

    def record_outcome(self, cap, engine, tier, ok, latency_ms, error=None) -> None:
        """公开包装：供 FabricHub 路由循环在真实流量下落盘（与 registry.route 同逻辑）。"""
        self._record_outcome(cap, engine, tier, ok, latency_ms, error)

    @staticmethod
    def capability_to_str(cap) -> str:
        """公开包装：能力统一成字符串，供调用方（FabricHub）落盘时与预测端对齐。"""
        return FabricRegistry._cap_to_str(cap)

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
        eff_tier = tier or self.tier
        # 先按档位(高->低)保证「端云合作」第一维度；同档内再排序。
        # 同档内：learned 且 predictor 已训练 → 用预测成功概率（eff_tier 与落盘一致）；
        # 否则静态策略。
        cands.sort(key=lambda a: (
            TIER_RANK.get(self._tier_of(a), TIER_RANK[TIER_MEDIUM]),
            self._intra_tier_key(a, cap_str, eff_tier),
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
        cap_str = self._cap_to_str(req.capability)
        # 白盒进化闭环：learned 且数据够、且积累够新样本时，先自动重训一次。
        self.maybe_retrain()
        providers = self.providers_for(req.capability, req_tier)
        if not providers:
            return InvokeResult(ok=False, error=f"no live provider for {cap_str}")
        # 落盘用的有效档位：与 _intra_tier_key 预测时使用的档位一致，保证
        # 训练/预测两端 vocab 对齐（否则预测时档位维度永远不在 vocab → 恒回落 0.5）。
        eff_tier = req_tier or self.tier
        last_res: InvokeResult | None = None
        attempts: list[str] = []
        for p in providers:
            t0 = time.perf_counter()
            try:
                res = p.invoke(req)
            except Exception as e:  # noqa: BLE001 - 单个供给方崩溃不阻断协商
                dt = (time.perf_counter() - t0) * 1000.0
                self._record_outcome(cap_str, p.engine_id, eff_tier, False, dt, error=repr(e))
                attempts.append(f"{p.engine_id} raised: {e!r}")
                continue
            dt = (time.perf_counter() - t0) * 1000.0
            self._record_outcome(
                cap_str, p.engine_id, eff_tier, res.ok, dt,
                error=res.error if not res.ok else None,
            )
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
