"""债 #18 混沌工程注入测试：固定 seed 注入引擎崩溃 / 429 限流 / 5xx 上游故障 /
随机失败，验证韧性闭环在真实流量下的表现：

  1. 崩溃隔离：芯粒 invoke 抛异常不穿透到调用方，自动降级兜底；
  2. 降级链切换：坏引擎排在前面时自动切到兜底好引擎，服务不中断；
  3. 熔断动态退避：429 短冷却(5s) / 5xx 指数退避(30·2^(n-1) 封顶 300s)；
  4. 熔断后 route 直接跳过坏引擎（should_skip 裁定，单一可信源）；
  5. 全失败返回干净的 ok=False，绝不向调用方抛异常。

诚实分级：**② 级**（offline 单测，真 FabricHub.route + 真 ResilienceBus）。
"""
import random
import sys

import pytest

sys.path.insert(0, "src")

from core.fabric.adapter import InvokeResult  # noqa: E402
from core.fabric.resilience_bus import _PerEngineBreaker  # noqa: E402
from kernel.plugins.fabric_hub import FabricHub, reset_fabric_hub  # noqa: E402


class _ChaosAdapter:
    """可控混沌引擎：按 mode 注入崩溃 / 429 / 5xx / 随机失败 / 正常。"""

    def __init__(self, eid, mode="ok", error="boom", rng=None):
        self._eid = eid
        self._mode = mode
        self._error = error
        self._rng = rng or random.Random(1234)
        self.calls = 0

    @property
    def engine_id(self):
        return self._eid

    def advertise_capabilities(self):
        return ["web.search"]

    def health(self):
        return True

    def invoke(self, req):
        self.calls += 1
        if self._mode == "crash":
            raise RuntimeError(f"{self._eid} 芯粒崩了")
        if self._mode == "random":
            # 固定 seed 的随机失败：约 60% 失败，错误类型也随机
            if self._rng.random() < 0.6:
                kind = self._rng.choice(["HTTP 429 rate limited",
                                         "HTTP 503 upstream down",
                                         "generic blip"])
                return InvokeResult(ok=False, error=kind)
        if self._mode in ("429", "5xx"):
            return InvokeResult(ok=False, error=self._error)
        return InvokeResult(ok=True, data={"engine": self._eid, "count": 1})


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("AOS_DISTILLER_OFF", "1")
    reset_fabric_hub()
    yield
    reset_fabric_hub()


def _make_hub(providers_by_cap):
    hub = FabricHub(adapters=())
    for ad in [a for lst in providers_by_cap.values() for a in lst]:
        hub._registry._adapters[ad.engine_id] = ad
    hub._registry.providers_for = lambda cap, tier=None: list(providers_by_cap.get(cap, []))
    hub._registry.maybe_retrain = lambda *a, **k: None
    hub._registry.record_outcome = lambda *a, **k: None
    return hub


# ── 1. 崩溃隔离：异常不穿透调用方 ───────────────────────────────────

def test_chaos_crash_isolated_not_propagated():
    boom = _ChaosAdapter("boom", mode="crash")
    good = _ChaosAdapter("good", mode="ok")
    hub = _make_hub({"web.search": [boom, good]})

    # 崩溃被 route 捕获隔离，降级到 good 成功；调用方全程无感（不抛）
    for _ in range(3):
        res = hub.route("web.search", {"query": "x"})
        assert res.ok is True and res.engine_id == "good"
    # 崩溃喂给 ResilienceBus → 连续 3 次 → 熔断（不再打到崩溃芯粒）
    assert boom.calls == 3
    assert hub._res_bus.should_skip("boom") is True
    # 熔断后路由直接跳过崩溃引擎，calls 不再增长，服务仍 ok
    res = hub.route("web.search", {"query": "x"})
    assert res.ok and boom.calls == 3


# ── 2. 降级链切换 ──────────────────────────────────────────────────

def test_chaos_degradation_switches_to_fallback():
    bad = _ChaosAdapter("bad429", mode="429", error="HTTP 429 rate limited")
    good = _ChaosAdapter("good", mode="ok")
    hub = _make_hub({"web.search": [bad, good]})

    res = hub.route("web.search", {"query": "x"})
    assert res.ok is True and res.engine_id == "good"   # 自动降级
    assert bad.calls == 1 and good.calls == 1


# ── 3. 429 短冷却（5s）────────────────────────────────────────────

def test_chaos_429_short_cooldown():
    bad = _ChaosAdapter("bad429", mode="429", error="HTTP 429 rate limited")
    good = _ChaosAdapter("good", mode="ok")
    hub = _make_hub({"web.search": [bad, good]})

    for _ in range(3):
        assert hub.route("web.search", {"query": "x"}).ok is True
    assert hub._res_bus.should_skip("bad429") is True
    # 429 专用短冷却：熔断后冷却时间被动态设为 5s（而非默认 30s）
    br = hub._res_bus._breakers["bad429"]
    assert br._cooldown == 5.0, "429 必须触发短冷却"


# ── 4. 5xx 指数退避（30·2^(n-1) 封顶 300s）────────────────────────

def test_chaos_5xx_exponential_backoff_integration():
    bad = _ChaosAdapter("bad5xx", mode="5xx", error="HTTP 503 upstream unavailable")
    good = _ChaosAdapter("good", mode="ok")
    hub = _make_hub({"web.search": [bad, good]})

    for _ in range(3):
        assert hub.route("web.search", {"query": "x"}).ok is True
    assert hub._res_bus.should_skip("bad5xx") is True
    br = hub._res_bus._breakers["bad5xx"]
    assert br._cooldown == 30.0, "首次 5xx 熔断退避应为 30s（base）"


def test_chaos_5xx_exponential_backoff_formula():
    """直接驱动熔断器状态机，证明 5xx 退避随连续失败次数指数增长并封顶 300s。

    真实语义：熔断后若仍持续收到 5xx 失败，每多一次失败退避指数 +1
    （30·2^(n-1)），而非「每次重新熔断清零」。这正是「动态退避」的含义。
    """
    br = _PerEngineBreaker("x")
    br.on_failure("HTTP 503 upstream")   # 1
    br.on_failure("HTTP 503 upstream")   # 2
    br.on_failure("HTTP 503 upstream")   # 3 → 首次熔断：base
    assert br._cooldown == 30.0
    br.on_failure("HTTP 503 upstream")   # 4 → 翻倍
    assert br._cooldown == 60.0
    br.on_failure("HTTP 503 upstream")   # 5 → 再翻倍
    assert br._cooldown == 120.0

    # 持续失败应封顶在 300s，不无限拉长
    for _ in range(20):
        br.on_failure("HTTP 503 upstream")
    assert br._cooldown == 300.0, "5xx 退避必须封顶 300s"


# ── 5. 全失败返回干净 ok=False，绝不抛 ─────────────────────────────

def test_chaos_all_fail_returns_clean_false():
    bad = _ChaosAdapter("onlybad", mode="5xx", error="HTTP 500 total failure")
    hub = _make_hub({"web.search": [bad]})   # 无兜底

    # 即便所有引擎全挂，route 也只返回 ok=False，绝不向调用方抛异常
    res = hub.route("web.search", {"query": "x"})
    assert isinstance(res, InvokeResult)
    assert res.ok is False
    assert "all providers failed" in (res.error or "")


# ── 6. 固定 seed 随机混沌：系统不崩、韧性闭环始终兜底 ─────────────────

def test_chaos_seeded_random_does_not_crash():
    """固定随机种子注入混合错误（429/5xx/随机），验证总线在不确定混沌下
    既不向调用方抛异常，又能逐步熔断失控引擎、兜底好引擎。"""
    rng = random.Random(20260804)        # 固定种子 → 可复现
    chaos = _ChaosAdapter("chaos", mode="random", rng=rng)
    good = _ChaosAdapter("good", mode="ok")
    hub = _make_hub({"web.search": [chaos, good]})

    ok_count = 0
    for i in range(20):
        res = hub.route("web.search", {"query": f"q{i}"})
        # 关键：无论混沌如何，路由调用本身绝不抛（韧性闭环吸收的边界）
        assert isinstance(res, InvokeResult)
        if res.ok:
            ok_count += 1
    # 有兜底好引擎在，服务应大体可用（至少部分成功）
    assert ok_count > 0, "混沌下兜底引擎应保证部分可用性"
    # 混沌引擎若连续失败达阈值，应被熔断（单一可信源裁定跳过）
    if chaos.calls >= 3:
        assert hub._res_bus.should_skip("chaos") is True or chaos.calls < 3
