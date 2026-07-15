"""IMA 结构化交接 — SubAgentRegistry 注册路径集成测试（真调 IMA OpenAPI）。

验证目标：HTTP 端点 /api/ima/execute 内部即 brain.subagents.invoke("ima", payload)，
而 brain.subagents 是 SubAgentRegistry 实例；本测试用真实的 SubAgentRegistry 类 +
真实的 IMASubagent/IMASkill，走完整 store_handoff -> get_handoff 闭环，确保这条
「端点注册路径」真实可用（不依赖重型 brain.get_brain() 构造，也不 mock 网络）。

副作用：会真实写入一条 IMA 笔记（标题含 TEST-可删除），可在 IMA 删除。
前置：D:\\AOS\\.env 配置 IMA_OPENAPI_CLIENTID + IMA_OPENAPI_APIKEY；未配置则整体 skip。
"""
from __future__ import annotations

import sys

sys.path.insert(0, "D:/AOS/src")

import pytest

from subagents.registry import SubAgentRegistry
from subagents.ima_agent import register_ima_subagent
from skills.ima import IMASkill

# 在 import 阶段即判定 IMA 是否配置；未配置则整个模块 skip（不触网）。
_configured = IMASkill().is_configured()
pytestmark = pytest.mark.skipif(not _configured, reason="IMA 未配置 API Key；配置 .env 后运行集成测试")


def _find_note_id(obj):
    """在可能多层嵌套的 IMA 响应里稳健提取 note_id / doc_id。"""
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if o.get("note_id"):
                return o["note_id"]
            if o.get("doc_id"):
                return o["doc_id"]
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return None


def test_ima_handoff_via_registry():
    """经 SubAgentRegistry 注册路径：store_handoff 写 -> get_handoff 读回一致。"""
    reg = SubAgentRegistry()
    register_ima_subagent(reg)
    assert reg.has("ima"), "IMA 子智能体应已注册"

    payload = {
        "operation": "store_handoff",
        "input": "",
        "title": "TEST-可删除",
        "summary": "SubAgentRegistry 注册路径集成测试（等价 /api/ima/execute 内部）",
        "confirmed_facts": [
            "HTTP 端点 handler 内部即 brain.subagents.invoke('ima', payload)",
            "SubAgentRegistry.invoke 是薄封装：查表 -> 调 IMASubagent.handle",
        ],
        "assumptions": ["注册路径不依赖重型 brain.get_brain() 构造"],
        "risk_boundary": ["不伪造知识结果"],
        "open_questions": ["注册路径直达 IMA"],
        "handoff_to": "下一手会话",
        "source": "tests/test_ima_handoff_registry.py",
        "tags": ["handoff", "registry", "test"],
    }

    # store
    r = reg.invoke("ima", payload)
    assert r.get("success") is True, f"registry.invoke 外层失败: {r}"
    data = r.get("data") or {}
    assert data.get("success") is True, f"IMA 业务层失败: {data}"
    note_id = _find_note_id(data)
    assert note_id, f"store_handoff 应返回 note_id，实际 data={data}"

    # get（读回并解析回信封）
    g = reg.invoke("ima", {"operation": "get_handoff", "input": "", "doc_id": note_id})
    gd = g.get("data") or {}
    assert gd.get("success") is True, f"get_handoff 失败: {gd}"
    env = gd.get("envelope") or {}
    assert env.get("title") == payload["title"], f"读回标题不一致: {env.get('title')}"
    assert len(env.get("confirmed_facts") or []) >= 1, "读回应含已确认事实"


if __name__ == "__main__":
    # 直接运行（不依赖 pytest 框架）：python tests/test_ima_handoff_registry.py
    if not _configured:
        print("SKIP: IMA 未配置 API Key")
        raise SystemExit(0)
    test_ima_handoff_via_registry()
    print("IMA 注册路径集成测试通过")
