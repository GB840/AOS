"""SearchAdapter（DuckDuckGo / ddgs）测试：免 key 真搜索接入 fabric。

不真实联网（mock DDGS），只验证：能力注册、产出可被下游消费的 content 摘要、
plan_bridge 把「搜索/查/找」路由到 web.search、缺 query 优雅降级。
"""
from __future__ import annotations

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import search_adapter as m


class _FakeDDGS:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def text(self, q, max_results=5, region="wt-wt"):
        return [
            {"title": f"{q} 结果1", "href": "http://e1", "body": "晴 26度"},
            {"title": f"{q} 结果2", "href": "http://e2", "body": "夜间 15度"},
        ]

    def news(self, *a, **k):
        return []


@pytest.fixture
def fake_ddgs(monkeypatch):
    monkeypatch.setattr(m, "DDGS", _FakeDDGS)
    yield


def test_search_adapter_advertises_web_search():
    a = m.SearchAdapter()
    assert Capability.WEB_SEARCH in a.advertise_capabilities()
    # health 反映 ddgs 是否可用（沙箱已装 → True）
    assert a.health() is True


def test_search_adapter_returns_content_summary(fake_ddgs):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert "content" in res.data
    assert "晴" in res.data["content"]          # 下游 media.image 经 in_from:previous 直接消费
    assert res.data["query"] == "北京天气"
    assert res.data["count"] == 2


def test_search_adapter_accepts_task_field(fake_ddgs):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"task": "上海温度"})
    )
    assert res.ok is True
    assert res.data["query"] == "上海温度"


def test_search_adapter_missing_query():
    res = m.SearchAdapter().invoke(InvokeRequest(capability="web.search", payload={}))
    assert res.ok is False
    assert "query" in res.error


def test_plan_bridge_maps_search_to_web_search():
    from kernel.plugins.plan_bridge import heuristic_plan

    caps = ["web.search", "media.image", "inference.llm", "action.aci"]
    steps = heuristic_plan("搜索天气并画一张示意图", caps)
    assert steps[0]["capability"] == "web.search"
    assert steps[0]["in"] == {"task": "搜索天气"}
    assert steps[1]["capability"] == "media.image"
    assert steps[1].get("in_from") == "previous"


def test_fabric_hub_registers_search():
    from kernel.plugins.fabric_hub import FabricHub

    hub = FabricHub(adapters=(m.SearchAdapter,))
    assert hub.resolve_engine("web.search") == "duckduckgo"
