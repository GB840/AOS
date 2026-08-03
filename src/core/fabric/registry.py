"""Capability-based registry & router.

AOS discovers engines by the CAPABILITIES they advertise, not by name.
When a task needs a capability, the registry picks the best live provider.

This is what makes AOS open and future-proof: swap or add any engine
(one of the four, or a future one) without touching core logic. The fabric
is a thin seam, not a heavy OS substrate.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict  # 修复 P1-2：补 typing 导入，避免 get_type_hints() 触发 NameError

logger = logging.getLogger(__name__)

from .adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from .capability import (
    Capability,
    TIER_HIGH,
    TIER_MEDIUM,
    TIER_LOW,
    TIER_AUTO,
    TIER_RANK,
)
from .route_outcome_store import RouteOutcomeStore, _MIN_SAMPLES
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
        distilled_memory_path: str | None = None,
        distilled_min_samples: int = 5,
        distilled_reliability_threshold: float = 0.5,
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
        # ── 白盒进化闭环·消费端（理念8）：把 MemoryDistiller 提炼出的
        # distilled_memory.jsonl 读回流式路由软偏好 ──
        # 仅当某 (能力,引擎) 的提炼成功率样本数 >= distilled_min_samples 且成功率
        # < distilled_reliability_threshold，才对该 (能力,引擎) 施加沉底惩罚（软偏好，
        # 仍作为兜底尝试，不硬阻断）。文件缺失/为空/样本不足/解析异常均零影响、不编造。
        self._distilled_path = distilled_memory_path
        self._distilled_min_samples = distilled_min_samples
        self._distilled_reliability_threshold = distilled_reliability_threshold
        self._distilled_penalties: dict[str, float] = {}
        self._distilled_mtime: float | None = None
        self._distilled_loaded = False
        self.reload_distilled()  # 启动即加载（无文件则空，零影响）

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

        末尾叠加白盒蒸馏惩罚：某 (能力,引擎) 被蒸馏记忆判定为「不可靠」
        （样本足、成功率低）时沉底，但仍是兜底候选（软偏好，不硬阻断）。
        """
        if (self.strategy == "learned" and self.predictor is not None
                and self.predictor.trained):
            base = -self.predictor.predict(cap_str, a.engine_id, tier or self.tier)
        else:
            base = self._sort_key(a)
        pen = (self._distilled_penalties.get(f"{cap_str}|{a.engine_id}", 0.0)
               + self._distilled_penalties.get(f"{cap_str}|*", 0.0))
        return base + pen

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
        # 白盒闭环·消费端：每次路由先按文件 mtime 增量重加载蒸馏记忆
        # （蒸馏器常驻持续写，这里让路由软偏好「越跑越新」，闭环真正活起来）。
        self._maybe_reload_distilled()
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

    # ---- 白盒进化闭环·消费端：蒸馏记忆 → 路由软偏好 ----------------
    def reload_distilled(self) -> None:
        """全量重加载 distilled_memory.jsonl，重建「不可靠 (能力,引擎) → 惩罚」表。

        best-effort、零副作用：文件缺失/为空/解析异常都清空惩罚并静默返回，
        绝不抛、绝不编造（理念6）。仅对样本数 >= distilled_min_samples 且成功率
        < distilled_reliability_threshold 的 (能力,引擎) 施加沉底惩罚（软偏好）。
        """
        if not self._distilled_path:
            return
        try:
            st = os.stat(self._distilled_path)
            self._distilled_mtime = st.st_mtime
        except OSError:
            self._distilled_penalties = {}
            self._distilled_loaded = False
            return
        penalties: dict[str, float] = {}
        try:
            with open(self._distilled_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("category") != "capability_reliability":
                        continue
                    md = rec.get("metadata") or {}
                    total = md.get("total") or 0
                    ok = md.get("ok") or 0
                    if not isinstance(total, int) or total < self._distilled_min_samples:
                        continue  # 样本不足 → 不惩罚（置信门控）
                    rate = (ok / total) if total else 1.0
                    if rate >= self._distilled_reliability_threshold:
                        continue  # 可靠 → 不惩罚（偏好交给 predictor）
                    cap = md.get("capability")
                    engine = None
                    key = md.get("key")
                    if isinstance(key, str) and "/" in key:
                        cap, engine = key.split("/", 1)
                    if not cap:
                        continue
                    pk = f"{cap}|{engine}" if engine else f"{cap}|*"
                    # 失败率越高，惩罚越重（让不可靠引擎沉底，仍作兜底）
                    pen = (1.0 - rate) * 10000.0
                    penalties[pk] = max(penalties.get(pk, 0.0), pen)
        except Exception as e:  # noqa: BLE001 - 读取/解析异常不致命
            logger.warning("distilled reload failed (ignored): %s", e)
            return
        self._distilled_penalties = penalties
        self._distilled_loaded = True

    def _maybe_reload_distilled(self) -> None:
        """mtime 门控的增量重加载：文件未变则跳过，变了才 reload。"""
        if not self._distilled_path:
            return
        try:
            st = os.stat(self._distilled_path)
        except OSError:
            return
        if st.st_mtime != self._distilled_mtime:
            self.reload_distilled()

    def distilled_diagnostics(self) -> Dict[str, Any]:
        """只读快照：蒸馏记忆消费端状态（可观测，对应理念9 可验证即真理）。

        - path / loaded / 惩罚条目数 / 各 (能力,引擎) 惩罚分；
        - 诚实回落：未配置 path → enabled=False；无惩罚 → penalties={}。
        """
        return {
            "enabled": self._distilled_path is not None,
            "path": self._distilled_path,
            "loaded": self._distilled_loaded,
            "min_samples": self._distilled_min_samples,
            "reliability_threshold": self._distilled_reliability_threshold,
            "penalty_count": len(self._distilled_penalties),
            "penalties": dict(self._distilled_penalties),
        }

    def record_outcome(self, cap, engine, tier, ok, latency_ms, error=None) -> None:
        """公开包装：供 FabricHub 路由循环在真实流量下落盘（与 registry.route 同逻辑）。"""
        self._record_outcome(cap, engine, tier, ok, latency_ms, error)

    @staticmethod
    def capability_to_str(cap) -> str:
        """公开包装：能力统一成字符串，供调用方（FabricHub）落盘时与预测端对齐。"""
        return FabricRegistry._cap_to_str(cap)

    def predictor_diagnostics(self) -> Dict[str, Any]:
        """只读的路由预测器状态快照（可观测性）。

        不含任何副作用：不落盘、不训练、不改动 predictor 状态。
        让「learned 策略到底学了什么 / 多少样本 / 是否已训练 / 对各能力×引擎
        的预测成功概率」可查可验证（对应 AOS 第 9 条「可验证即真理」）。

        诚实回落：
        - 未注入 predictor → has_predictor=False、trained=False、词汇表全 0；
        - 未训练 → sample_predictions=[]（不假装给出了概率）；
        - 仅对训练集覆盖范围内的 (能力,引擎,档位) 给出学到的概率，否则诚实 0.5。
        """
        diag: Dict[str, Any] = {
            "strategy": self.strategy,
            "tier": self.tier,
            "has_predictor": self.predictor is not None,
            "trained": bool(self.predictor and self.predictor.trained),
            "outcome_store_connected": self.outcome_store is not None,
            "sample_count": self.outcome_store.count() if self.outcome_store else 0,
            "min_train_samples": _MIN_SAMPLES if self.outcome_store else None,
            "vocab_capabilities": len(self.predictor._vocab_cap) if self.predictor else 0,
            "vocab_engines": len(self.predictor._vocab_eng) if self.predictor else 0,
            "vocab_tiers": len(self.predictor._vocab_tier) if self.predictor else 0,
            "sample_predictions": [],
        }
        if self.predictor is not None and self.predictor.trained:
            preds = []
            for eid, adapter in self._adapters.items():
                for cap in adapter.advertise_capabilities():
                    cap_str = self.capability_to_str(cap)
                    p = self.predictor.predict(cap_str, eid, self.tier)
                    preds.append({
                        "capability": cap_str,
                        "engine": eid,
                        "tier": self.tier,
                        "p_success": round(p, 4),
                    })
            diag["sample_predictions"] = preds
        return diag

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

    def capabilities_of(self, engine_id: str) -> list[str]:
        """返回某引擎能服务的能力字符串列表（供 ResilienceBus 降级链查找）。"""
        a = self._adapters.get(engine_id)
        if a is None:
            return []
        return [self._cap_to_str(c) for c in a.advertise_capabilities()]

    def get(self, engine_id: str) -> "BaseAgentAdapter | None":
        """按 engine_id 取已注册适配器（进程内）。

        隔离引擎(B 路线子进程)由 FabricHub 单独持有，不在此返回。
        """
        return self._adapters.get(engine_id)
