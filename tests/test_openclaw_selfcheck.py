"""OpenClaw 适配器自检 / 自愈闭环测试（无需真实网关即可跑，沙箱可验证）。

覆盖：
  - health() 返回 bool
  - health_detail() 结构化死因（ok/port_down/binary_missing）+ 可操作 action
  - ensure_gateway() 在无 openclaw 二进制时干净返回 False（不抛、不卡死）
  - FabricHub.health_report() 给 openclaw 附 health_detail 字段
"""
import sys

sys.path.insert(0, "D:/AOS/src")

from core.fabric.adapters.openclaw_adapter import (
    OpenClawAdapter,
    _resolve_openclaw_mjs,
)


def test_health_returns_bool():
    assert isinstance(OpenClawAdapter().health(), bool)


def test_health_detail_structure_and_no_crash():
    d = OpenClawAdapter().health_detail()
    assert set(d.keys()) >= {"status", "reason", "action"}
    assert d["status"] in ("ok", "port_down", "binary_missing")


def test_health_detail_action_present_when_down():
    d = OpenClawAdapter().health_detail()
    if d["status"] != "ok":
        assert d["action"] and "openclaw" in d["action"].lower()


def test_ensure_gateway_clean_fail_without_binary(monkeypatch):
    a = OpenClawAdapter()
    monkeypatch.setattr(
        "core.fabric.adapters.openclaw_adapter._resolve_openclaw_mjs",
        lambda: None,
    )
    # 无二进制：不抛、不卡死，直接 False
    assert a.ensure_gateway(timeout=2) is False


def test_resolve_openclaw_mjs_returns_none_or_path():
    r = _resolve_openclaw_mjs()
    assert r is None or isinstance(r, str)


def test_health_report_includes_health_detail():
    from kernel.plugins.fabric_hub import FabricHub

    rep = FabricHub().health_report()
    oc = rep["adapters"].get("openclaw")
    assert oc is not None, "openclaw 应在默认 fabric 中注册"
    assert "health_detail" in oc
    assert set(oc["health_detail"].keys()) >= {"status", "reason", "action"}
