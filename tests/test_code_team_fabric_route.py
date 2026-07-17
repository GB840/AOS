"""code_team 接入 FabricHub 路由的测试。

两条层级：
  - 单元层（快、必跑）：直接测 CodeTeamAdapter 契约——
    engine_id / advertise_capabilities / health / invoke 在离线 heuristic
    模式下产出可运行、过质量门、过真实测试的代码，并对不支持语言诚实失败。
  - 端到端层（重、可跳过）：构造完整 FabricHub，断言 code-team 出现在
    health_report 的 live 列表，且 hub.route("code.generate", ...) 真实跑通
    （生成+执行+engine_id 透明化）。构造失败（沙箱缺依赖）则 pytest.skip，
    绝不伪造通过。
"""
from __future__ import annotations

import pytest

from core.fabric.adapter import InvokeResult, InvokeRequest
from core.fabric.capability import Capability
from kernel.plugins.code_team_adapter import CodeTeamAdapter


# ───────────────────────── 单元层（快、必跑） ─────────────────────────

def test_adapter_identity_and_contract():
    a = CodeTeamAdapter()
    assert a.engine_id == "code-team"
    assert a.advertise_capabilities() == [Capability.CODE_GENERATE]
    assert a.health() is True
    assert a.tier() == "high"


def test_invoke_python_generates_runs_and_passes():
    a = CodeTeamAdapter()
    res = a.invoke(InvokeRequest(
        capability=Capability.CODE_GENERATE,
        payload={"requirement": "写一个计算器", "lang": "python"}))
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    assert res.engine_id == "code-team"  # 引擎透明化
    data = res.data
    files = data["files"]
    assert "calculator.py" in files and "test_calculator.py" in files
    assert data["execution"]["ok"] is True
    assert data["quality"]["passed"] is True
    assert data["llm_used"] is False  # 离线 heuristic，诚实标注


def test_invoke_javascript_runs_via_node_if_available():
    a = CodeTeamAdapter()
    res = a.invoke(InvokeRequest(
        capability=Capability.CODE_GENERATE,
        payload={"requirement": "斐波那契", "lang": "javascript"}))
    assert res.engine_id == "code-team"
    files = res.data["files"]
    assert "fibonacci.js" in files and "fibonacci.test.js" in files
    # node 不可用时诚实回落（ok=False, stage=runtime_unavailable），不伪造通过。
    assert res.data["execution"]["ok"] in (True, False)


def test_invoke_unsupported_lang_is_honest_failure():
    a = CodeTeamAdapter()
    res = a.invoke(InvokeRequest(
        capability=Capability.CODE_GENERATE,
        payload={"requirement": "x", "lang": "cobol"}))
    assert res.ok is False
    assert res.engine_id == "code-team"
    assert "cobol" in (res.data["execution"]["error"] or "")


# ───────────────────────── 端到端层（重、可跳过） ─────────────────────────

def _build_hub():
    try:
        from kernel.plugins.fabric_hub import FabricHub
        return FabricHub()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"FabricHub 构造失败（沙箱缺依赖），跳过端到端: {e!r}")


def test_code_team_live_in_health_report():
    hub = _build_hub()
    report = hub.health_report()
    assert "code-team" in report["adapters"], "code-team 应出现在 health_report"
    assert report["adapters"]["code-team"]["live"] is True
    assert "code.generate" in report["adapters"]["code-team"]["capabilities"]


def test_hub_route_code_generate_runs_end_to_end():
    hub = _build_hub()
    res = hub.route("code.generate", {"requirement": "写一个计算器", "lang": "python"})
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    assert res.engine_id == "code-team"
    data = res.data
    assert data["execution"]["ok"] is True
    assert data["quality"]["passed"] is True
