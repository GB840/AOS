"""锚定「端云合作 / 云端用不了就本地」是路由层的真实机制，而非口号。

验证了三件事：
1. 某供给方 ok=False 时，route 自动故障转移到下一个 live 供给方；
2. 供给方按偏好排序（云端优先→本地兜底），transfer 顺序可解释；
3. 全部失败时返回合并错误，且明确指出每个失败供给方。
"""
from __future__ import annotations

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from core.fabric.registry import FabricRegistry, PROVIDER_PREFERENCE


class _Fake(BaseAgentAdapter):
    def __init__(self, eid: str, caps, result: InvokeResult | Exception | None = None,
                 health: bool = True) -> None:
        self._eid = eid
        self._caps = caps
        self._result = result
        self._health = health
        self.calls = 0

    @property
    def engine_id(self) -> str:
        return self._eid

    def advertise_capabilities(self) -> list:
        return list(self._caps)

    def health(self) -> bool:
        return self._health

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        self.calls += 1
        if isinstance(self._result, Exception):
            raise self._result
        if self._result is None:
            return InvokeResult(ok=False, error="not implemented")
        return self._result


def _ok(eid):
    return InvokeResult(ok=True, data={"served_by": eid})


def test_failover_cloud_to_local():
    """云端供给方失败 → 自动降级本地供给方（端云合作的核心路径）。"""
    reg = FabricRegistry()
    reg.register(_Fake("agnes", [Capability.LLM_GATEWAY], InvokeResult(ok=False, error="cloud 503")))
    reg.register(_Fake("litellm", [Capability.LLM_GATEWAY], _ok("litellm")))  # 本地兜底
    # 偏好：agnes=10 优先，litellm=20 兜底
    assert PROVIDER_PREFERENCE.get("agnes", 50) < PROVIDER_PREFERENCE.get("litellm", 50)

    res = reg.route(InvokeRequest(capability=Capability.LLM_GATEWAY, payload={}))
    assert res.ok is True
    assert res.data["served_by"] == "litellm"


def test_failover_skips_raise_then_succeeds():
    """供给方抛异常也算失败，照常转移到下一个。"""
    reg = FabricRegistry()
    reg.register(_Fake("openclaw", [Capability.CHANNEL_ACCESS], RuntimeError("gw down")))
    reg.register(_Fake("agnes", [Capability.CHANNEL_ACCESS], _ok("agnes")))
    res = reg.route(InvokeRequest(capability=Capability.CHANNEL_ACCESS, payload={}))
    assert res.ok is True
    assert res.data["served_by"] == "agnes"


def test_all_fail_returns_merged_error():
    reg = FabricRegistry()
    reg.register(_Fake("openclaw", [Capability.CHANNEL_ACCESS], InvokeResult(ok=False, error="a down")))
    reg.register(_Fake("agnes", [Capability.CHANNEL_ACCESS], InvokeResult(ok=False, error="b down")))
    res = reg.route(InvokeRequest(capability=Capability.CHANNEL_ACCESS, payload={}))
    assert res.ok is False
    assert "openclaw" in res.error and "agnes" in res.error
    assert "all providers failed" in res.error


def test_no_live_provider_honest_error():
    reg = FabricRegistry()
    reg.register(_Fake("openclaw", [Capability.CHANNEL_ACCESS], _ok("x"), health=False))
    res = reg.route(InvokeRequest(capability=Capability.CHANNEL_ACCESS, payload={}))
    assert res.ok is False
    assert "no live provider" in res.error
