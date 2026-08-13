"""LNN 芯粒单元测试。

核心不弄虚验证：纯 numpy CfC 真的能学会正弦波（MSE 显著下降），证明 AOS 的
液态神经网络芯粒是在干自己擅长的时间序列活，而非假接口。
"""
from __future__ import annotations

import math

from core.fabric.adapters.lnn_adapter import LNNAdapter, _CfCNet
from core.fabric.adapters.lfm_adapter import LFMAdapter
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability


def test_cfc_learns_sine():
    """CfC 必须真实学会正弦（loss 下降 >50%）——梯度正确性的硬核查。"""
    S = [math.sin(0.3 * i) for i in range(60)]
    net = _CfCNet(in_size=1, hid_size=24, seed=42)
    losses = net.train(S, epochs=400, lr=0.02)
    assert losses[-1] < losses[0] * 0.5, f"LNN 没学会: {losses[0]} -> {losses[-1]}"
    # 自回归预测首值应接近真实正弦下一值（方向正确）
    fc = net.forecast(S, horizon=5)
    expected = math.sin(0.3 * 60)
    assert abs(fc[0] - expected) < 0.4, f"预测偏离: {fc[0]} vs {expected}"


def test_lnn_adapter_demo():
    r = LNNAdapter().invoke(InvokeRequest(
        capability="inference.lnn", payload={"demo": True, "horizon": 5, "epochs": 300}))
    assert r.ok is True
    d = r.data
    assert isinstance(d["forecast"], list) and len(d["forecast"]) == 5
    # 0.52 -> <0.35 表示明显学会（CfC 真实在学，非假接口）
    assert d["final_loss"] < 0.35, f"demo 未学成: {d['final_loss']}"
    # 引擎名：numpy 自包含时含 cfc/numpy；探测到 torch/ncps/liquidmind 时标 (available)
    assert d["engine"] and (
        "cfc" in d["engine"] or "numpy" in d["engine"] or "(available)" in d["engine"]
    ), d["engine"]


def test_lnn_adapter_linear_extrapolation():
    """LNN 捕获上升趋势即可（无界线性对微型 CfC 偏难，只验方向不验绝对值）。"""
    r = LNNAdapter().invoke(InvokeRequest(
        capability="inference.lnn",
        payload={"series": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "horizon": 4, "epochs": 300}))
    assert r.ok is True
    fc = r.data["forecast"]
    assert fc == sorted(fc), f"应呈上升/持平趋势: {fc}"
    assert fc[-1] > 6, fc  # 至少延续增长方向


def test_lnn_adapter_bad_input():
    r = LNNAdapter().invoke(InvokeRequest(
        capability="inference.lnn", payload={"series": [1, 2]}))
    assert r.ok is False  # 点数不足


def test_lnn_registered_in_kernel():
    # 避免重型构建：直接验证能力广告 + 引擎解析
    a = LNNAdapter()
    assert Capability.INFERENCE_LNN in a.advertise_capabilities()
    assert a.engine_id == "lnn"
    assert a.health() is True  # numpy 零依赖永远 live


def test_lfm_honest_not_live_by_default():
    """LFM2 默认未下载权重 → health() 诚实 False，绝不谎报 live。"""
    a = LFMAdapter()
    assert a.engine_id == "lfm2"
    assert Capability.LLM_GATEWAY in a.advertise_capabilities()
    assert a.health() is False
    det = a.health_detail()
    assert det["live"] is False
    assert det["runtime_available"] in (True, False)  # 不报错即可


def test_lnn_http_dispatch(monkeypatch):
    """进程内直调 handler，绕过沙箱残留服务进程干扰。

    FabricHub HTTP 面已强制 Bearer 鉴权（_check_auth fail-closed：
    未设 AOS_FABRIC_HTTP_TOKEN 直接 500），故这里注入测试 token 并带上
    Authorization 头，测的是路由分发本身而非鉴权。
    """
    import io
    from core.fabric.http_server import FabricHubHTTPHandler

    token = "test-lnn-token"
    monkeypatch.setenv("AOS_FABRIC_HTTP_TOKEN", token)

    def make_handler(path, body=None):
        h = FabricHubHTTPHandler.__new__(FabricHubHTTPHandler)
        h.path = path
        h.headers = {
            "Content-Length": str(len(body or b"")),
            "Authorization": f"Bearer {token}",
        }
        h.rfile = io.BytesIO(body or b"")
        h.wfile = io.BytesIO()
        h._code = 200
        h.send_response = lambda c: None
        h.send_header = lambda k, v: None
        h.end_headers = lambda: None
        return h

    # /api/lnn/info
    h = make_handler("/api/lnn/info")
    h.do_GET()
    info = __import__("json").loads(h.wfile.getvalue().decode())
    assert info["ok"] is True
    assert info["lnn"]["live"] is True

    # /api/lnn/predict (demo, 少量 epoch 提速)
    import json
    b = json.dumps({"demo": True, "horizon": 3, "epochs": 120}).encode()
    h2 = make_handler("/api/lnn/predict", b)
    h2.do_POST()
    out = json.loads(h2.wfile.getvalue().decode())
    assert out["ok"] is True
    assert len(out["forecast"]) == 3


def test_companion_lnn_intent():
    """伙伴能识别预测意图并走 LNN 路由（用 mock 隔离重型 hub）。"""
    import core.fabric.companion as C

    intent = C.Companion.route_intent(
        C.Companion("default"), "预测一下 1,2,3,4,5,6,7,8")
    assert intent["kind"] == "lnn"
    assert intent["payload"]["series"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]

    # mock _route_hub，验证 lnn 分支产出预测文案
    orig = C._route_hub
    C._route_hub = lambda cap, pl: {"ok": True, "data": {
        "forecast": [8.5, 8.7, 8.9, 9.1, 9.3], "engine": "cfc-numpy", "final_loss": 0.1}}
    try:
        res = C.handle_companion_message("预测 1 2 3 4 5 6 7 8", "default")
        assert res["ok"] is True
        assert "液态神经网络" in res["reply"]
        assert "8.5" in res["reply"]
    finally:
        C._route_hub = orig
