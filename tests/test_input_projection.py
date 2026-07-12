"""流水线 input 投影 + mem0 输入容错的回归测试。

验证：(1) OrchestrationChiplet 在 in_from:previous 时把上游产出投影出 text
字段，让 channel.access 不再收到空 message；(2) mem0 adapter 在 query/text
缺失时从上游产出兜底提取，不再报 "Invalid query empty"。
"""
import pytest

from core.fabric.adapter import InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
from core.fabric.adapters.mem0_adapter import Mem0Adapter


def test_orchestration_projects_text_to_channel_access():
    captured = {}

    def route(cap, payload):
        captured[cap] = payload
        if cap == "web.search":
            return InvokeResult(ok=True, data={"content": "北京 28℃",
                                              "query": "北京天气", "engine": "baidu", "count": 3})
        if cap == "media.image":
            return InvokeResult(ok=True, data={"images": [{"url": "https://img/x.png"}],
                                              "model": "agnes-image-2.1-flash"})
        if cap == "channel.access":
            return InvokeResult(ok=True, data={"reply": "sent"})
        return InvokeResult(ok=False, error="no engine")

    oc = OrchestrationChiplet(route_fn=route)
    spec = {"steps": [
        {"capability": "web.search", "in": {"task": "北京天气"}},
        {"capability": "media.image", "in_from": "previous"},
        {"capability": "channel.access", "in_from": "previous"},
    ]}
    res = oc.invoke(InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload=spec))
    assert res.ok, res.error
    # channel.access 必须拿到非空 text（来自 media.image 的图 URL），而非空 message
    assert "text" in captured["channel.access"]
    assert captured["channel.access"]["text"].strip()
    assert "https://img/x.png" in captured["channel.access"]["text"]


class _FakeMem:
    def __init__(self):
        self.calls = []

    def add(self, text, **kw):
        self.calls.append(("add", text))
        return {"ok": True, "text": text}

    def search(self, query, **kw):
        self.calls.append(("search", query))
        return {"ok": True, "query": query}

    def get(self, *a, **kw):
        return {}

    def get_all(self, **kw):
        return {}


def test_mem0_search_falls_back_to_text(monkeypatch):
    fake = _FakeMem()
    import core.fabric.adapters.mem0_adapter as mm
    monkeypatch.setattr(mm, "_build_memory", lambda M, c: fake)
    # 模拟 in_from:previous 透传的 media.image out（images 是字符串）
    payload = {"images": "[{'url': 'https://img/x.png'}]"}
    res = Mem0Adapter().invoke(InvokeRequest(capability=Capability.MEMORY_SEMANTIC, payload=payload))
    assert res.ok, res.error
    assert fake.calls[0][0] == "search"
    assert "https://img/x.png" in fake.calls[0][1]  # query 兜底，不再 Invalid query


def test_mem0_add_uses_extracted_text(monkeypatch):
    fake = _FakeMem()
    import core.fabric.adapters.mem0_adapter as mm
    monkeypatch.setattr(mm, "_build_memory", lambda M, c: fake)
    payload = {"action": "add", "images": "[{'url': 'https://img/x.png'}]"}
    res = Mem0Adapter().invoke(InvokeRequest(capability=Capability.MEMORY_SEMANTIC, payload=payload))
    assert res.ok, res.error
    assert fake.calls[0][0] == "add"
    assert "https://img/x.png" in fake.calls[0][1]
