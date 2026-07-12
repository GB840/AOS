"""SearchAdapter 多源 fallback 测试：智谱联网优先 → DuckDuckGo 直连 → Jina 兜底。

不真实联网（monkeypatch 各 _search_*），只验证：能力注册、产出可被下游消费的
content 摘要、fallback 顺序（智谱挂则跳 DDG）、全失败优雅报错、plan_bridge 路由、
hub 注册。
"""
from __future__ import annotations

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import search_adapter as m


def _zhipu_ok(self, query, n):
    return {"content": f"{query} 智谱联网结果：晴 26度",
            "query": query,
            "results": [{"title": "天气", "url": "http://z", "body": "晴 26度"}],
            "count": 1}


def _zhipu_fail(self, query, n):
    raise RuntimeError("ZHIPU_API_KEY 未配置")


def _ddg_ok(self, query, n):
    return {"content": f"{query} DDG结果", "query": query,
            "results": [{"title": "r", "url": "http://d", "body": "晴"}], "count": 1}


def _jina_ok(self, query, n):
    return {"content": f"{query} jina结果", "query": query,
            "results": [{"title": "j", "url": "http://j", "body": "晴"}], "count": 1}


@pytest.fixture
def patch_all_ok(monkeypatch):
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _zhipu_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _ddg_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    yield


def test_search_adapter_advertises_web_search():
    a = m.SearchAdapter()
    assert Capability.WEB_SEARCH in a.advertise_capabilities()
    assert a.health() is True


def test_search_adapter_returns_content_summary(patch_all_ok):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert "content" in res.data
    assert "晴" in res.data["content"]
    assert res.data["query"] == "北京天气"
    assert res.data["engine"] == "zhipu"      # 智谱优先
    assert res.data["count"] == 1


def test_search_adapter_accepts_task_field(patch_all_ok):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"task": "上海温度"})
    )
    assert res.ok is True
    assert res.data["query"] == "上海温度"


def test_search_adapter_fallback_to_ddg(monkeypatch):
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _zhipu_fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _ddg_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert res.data["engine"] == "duckduckgo"   # 智谱挂 → 跳 DDG


def test_search_adapter_all_fail(monkeypatch):
    def _fail(self, q, n):
        raise RuntimeError("boom")
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _fail)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "x"})
    )
    assert res.ok is False
    assert "所有搜索源均失败" in res.error


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
    assert hub.resolve_engine("web.search") == "web-search"
