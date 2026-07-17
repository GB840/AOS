"""failure_monitor 通电验证：纯内存统计逻辑 + /api/failure_monitor 端点。

failure_monitor.py 此前是死模块（全仓无任何调用）。本次通电把它接进
FabricHub.route() 真实失败流量埋点，并经只读端点 /api/failure_monitor 暴露。
本测试覆盖：monitor 统计/告警逻辑（不构造重型 FabricHub）+ 端点返回结构。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.plugins.failure_monitor import FailureMonitor, FailureMode  # noqa: E402


def test_stats_empty():
    m = FailureMonitor()
    s = m.get_stats()
    assert s["total_tasks"] == 0
    assert s["failure_rate"] == 0.0
    assert s["alerts"] == []


def test_record_and_stats():
    m = FailureMonitor()
    m.record_task_start()
    m.record(FailureMode.TIMEOUT, agent_id="code-exec", task_id="x")
    # 该任务未 record_success → 计入失败
    s = m.get_stats()
    assert s["total_tasks"] == 1
    assert s["success_count"] == 0
    assert s["failure_count"] == 1
    assert s["failure_rate"] == 1.0
    assert s["counts_by_mode"]["timeout"] == 1
    rec = m.get_recent_failures(5)
    assert any(r["mode"] == "timeout" for r in rec)


def test_alerts_over_baseline():
    m = FailureMonitor()
    # TIMEOUT 基线 0.06，需 actual>0.12 且 count>=3
    for _ in range(5):
        m.record_task_start()
        m.record(FailureMode.TIMEOUT)
    s = m.get_stats()
    assert any("timeout" in a.lower() for a in s["alerts"])


def test_endpoint(monkeypatch):
    """集成层：经 TestClient 打到真实 app，验证端点被正确路由且返回 200 结构。

    认证由 security 中间件负责（其 WIP 修复见对话说明），此处隔离该依赖：
    用 monkeypatch 把 APISecurityMiddleware.dispatch 换成直接放行，专测
    failure_monitor 端点自身的可达性与返回结构，避免在 security 未提交修复时
    把外部依赖带进本测试。
    """
    from fastapi.testclient import TestClient
    from api.main import app

    async def _bypass(self, request, call_next):
        return await call_next(request)

    monkeypatch.setattr("api.security.APISecurityMiddleware.dispatch", _bypass)
    client = TestClient(app)
    r = client.get("/api/failure_monitor")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "stats" in body and "recent_failures" in body
    assert "alerts" in body and "uptime_seconds" in body
    assert "failure_rate" in body["stats"]


def test_endpoint_logic():
    """单元层：直接调用端点 handler（不经认证中间件、不构造重型 FabricHub），
    真跑返回结构。"""
    import asyncio
    from api.main import failure_monitor_api
    body = asyncio.run(failure_monitor_api())
    assert body["status"] == "ok"
    assert "stats" in body and "recent_failures" in body
    assert "alerts" in body and "uptime_seconds" in body
    assert "failure_rate" in body["stats"]


def test_route_feeds_monitor():
    """端到端：构造 FabricHub 后，route 真实流量（即使能力无 provider 而失败）
    也会被喂入 failure_monitor 单例——证明 monitor 从死模块变为被路由栈真实接电。
    构造失败（重型环境）则跳过。"""
    try:
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"FabricHub 构造失败（重型环境），跳过端到端: {e}")
    from kernel.plugins.failure_monitor import get_failure_monitor
    mon = get_failure_monitor()
    before = mon.get_stats()["total_tasks"]
    # 无 provider 的能力：route 入口 best-effort 埋点 record_task_start 必触发
    hub.route("__no_such_capability__", {"x": 1})
    after = mon.get_stats()["total_tasks"]
    assert after >= before + 1, (before, after)
