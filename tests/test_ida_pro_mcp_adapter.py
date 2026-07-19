"""本机 IDA Pro 逆向工程 MCP 适配器测试：localhost 红线 / 能力映射 / 工具调用。"""
import sys

sys.path.insert(0, "D:/AOS/src")

import pytest

from core.fabric.adapters.ida_pro_mcp_adapter import IdaProMcpAdapter, _host_of
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability


def _fake_rpc(method, params=None, notif=False):
    if notif:
        return None
    if method == "initialize":
        return {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "ida-pro-mcp"}}
    if method == "tools/list":
        return {"tools": [{"name": "get_metadata"}, {"name": "decompile_function"}]}
    if method == "tools/call":
        name = (params or {}).get("name")
        if name == "get_metadata":
            return {"content": [{"type": "text", "text": "IDA v9.3, functions=1234"}]}
        if name == "decompile_function":
            return {"content": [{"type": "text", "text": "int main() { return 0; }"}]}
    return {"content": []}


def test_host_of_parsing():
    assert _host_of("http://localhost:13337/mcp") == "localhost"
    assert _host_of("http://127.0.0.1/mcp") == "127.0.0.1"
    assert _host_of("http://8.8.8.8/mcp") == "8.8.8.8"


def test_advertises_re_ida():
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    assert ad.advertise_capabilities() == [Capability.RE_IDA]


def test_localhost_only_red_line():
    ad = IdaProMcpAdapter(server_url="http://8.8.8.8/mcp")
    assert ad.is_localhost is False
    assert ad.health() is False
    res = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={"tool": "get_metadata"}))
    assert res.ok is False and "localhost" in (res.error or "")


def test_invoke_get_metadata_and_decompile():
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r1 = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={"tool": "get_metadata"}))
    assert r1.ok and "IDA v9.3" in r1.data["text"]
    r2 = ad.invoke(InvokeRequest(capability=Capability.RE_IDA,
                                 payload={"tool": "decompile_function", "arguments": {"address": 0x1000}}))
    assert r2.ok and "int main" in r2.data["text"]


def test_default_tool_is_get_metadata():
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={}))
    assert r.ok and "IDA v9.3" in r.data["text"]


def test_fabrichub_register_refuses_non_localhost():
    # 集成：FabricHub 在 URL 非 localhost 时应拒绝注册（红线），localhost 时注册成功。
    try:
        from kernel.plugins.fabric_hub import FabricHub
    except Exception as e:  # noqa: BLE001 - 重型依赖缺失则跳过，不拖垮套件
        pytest.skip(f"FabricHub 不可用（重型依赖）: {e}")
    hb = FabricHub(adapters=())
    assert hb.register_ida_pro_mcp(url="http://8.8.8.8/mcp") is None
    eid = hb.register_ida_pro_mcp(url="http://localhost:13337/mcp")
    assert eid == "ida-pro-mcp"
    provs = hb._registry.providers_for(Capability.RE_IDA, "high")
    assert any(p.engine_id == "ida-pro-mcp" for p in provs)


def test_invoke_refuses_write_without_optin():
    # D3：写操作（rename/comment...）默认只读红线拦截，需显式 read_only=False。
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA,
                                payload={"tool": "rename", "arguments": {"address": 1, "new_name": "x"}}))
    assert r.ok is False and "read_only" in (r.error or "")


def test_invoke_allows_write_with_optin():
    # D3：显式 read_only=False 后写操作放行。
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA,
                                payload={"tool": "rename", "arguments": {}, "read_only": False}))
    assert r.ok is True


def test_invoke_refuses_dbg_unsafe():
    # D3：调试类 unsafe 工具（dbg_*）即便显式 opt-in 也永久拒绝。
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={"tool": "dbg_breakpoint"}))
    assert r.ok is False and "unsafe" in (r.error or "")


def test_invoke_records_read_only_mode():
    # D3：默认只读，返回数据标注 read_only 供上层审计。
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={"tool": "get_metadata"}))
    assert r.ok and r.data.get("read_only") is True


def test_explain_unsafe_tools_returns_risk_map():
    # 红线「永久拒绝 dbg_*」必须可解释：能查到拒了什么、开销/风险多大。
    risk = IdaProMcpAdapter.explain_unsafe_tools()
    assert "memory_write" in risk and "control" in risk
    # 最高危的 dbg_write 在 memory_write 类，明确标注「极高」风险
    assert "dbg_write" in risk["memory_write"]["tools"]
    assert risk["memory_write"]["risk"].startswith("极高")
    # 非 dbg_ 但同样危险的 py_eval 也列入（任意 Python 代码损坏 IDB）
    assert "py_eval" in risk["arbitrary_code"]["tools"]


def test_invoke_dbg_reports_risk_summary():
    # D3：拒绝 dbg_* 时附带可复核的风险摘要（诚实非黑箱拒绝）。
    ad = IdaProMcpAdapter(server_url="http://localhost:13337/mcp", transport_fn=_fake_rpc)
    r = ad.invoke(InvokeRequest(capability=Capability.RE_IDA, payload={"tool": "dbg_write"}))
    assert r.ok is False
    assert r.data.get("blocked_reason") == "unsafe_debug_tool"
    assert "dbg_write" in (r.data.get("unsafe_risk_summary") or "")
    assert "?ext=dbg" in (r.data.get("unsafe_risk_summary") or "")
