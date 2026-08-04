"""系统级指标端点单测（#20 /metrics/system 收口验证）。

覆盖：
  * GET /metrics/system → 200，text/plain，含 resilience + pulse 指标行
  * ResilienceBus 未挂载时 resilience 指标归零，不抛 500
  * GET /health 存活探针秒回，结构不变（向后兼容）

诚实分级：②（代码+单测实证）。用 TestClient 直接打端点，不触发 lifespan 启动。
"""

import sys
sys.path.insert(0, "D:/AOS/src")

from fastapi.testclient import TestClient

from api.main import app


def test_metrics_system_ok():
    """/metrics/system 返回 Prometheus 风格文本，含 resilience 与 pulse 指标。"""
    client = TestClient(app)
    resp = client.get("/metrics/system")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")
    body = resp.text
    # resilience 指标（bus 未挂载 → 归零）
    assert "aos_resilience_circuit_trips 0" in body
    assert "aos_resilience_open_circuits 0" in body
    # 类型/帮助注释存在
    assert "# TYPE aos_resilience_circuit_trips counter" in body
    # pulse 概要（best-effort，至少出现指标名）
    assert "aos_pulse_workflows_total" in body


def test_health_still_alive():
    """/health 存活探针向后兼容，秒回且结构不变。"""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("status") == "alive"
    assert data.get("service") == "aos"
