"""API 层集成测试：验证渲染/A2UI 端点的接线正确性。

为何不走完整 TestClient：
  api.main 的 startup 事件会做数据库连接池、上游可达性探测(probe_upstreams)、
  v5 kernel mount 等——这些在沙箱无外网 egress 时会 DNS 挂死不超时（实测卡
  11 分钟）。故本文件**不触发 startup**，改用两种等价且沙箱可跑的验证：
    1) 路由注册断言：app.routes 中存在对应 path+method，证明端点确实注册、
       未被接错 import 吞掉（import 失败会导致路由缺失）。
    2) 直接调用 handler 函数（async，不依赖 startup 副作用）：验证返回值/
       响应头/内容正确，证明 import 链、响应构造、A2UI 渲染在真实运行路径上
       无错。

这覆盖了函数单测抓不到的「端点层」问题（路由缺失、import 接错、响应头不对、
函数返回未被正确包裹），只是不验证 ASGI 中间件/生命周期这一薄层（沙箱限制，
已诚实说明）。
"""
import asyncio
import os

import pytest

# 沙箱无真实 LLM → 强制关闭，走确定性 heuristic。
os.environ.setdefault("AOS_CODETEAM_LLM", "0")

from api.main import (  # noqa: E402
    app,
    a2ui_demo,
    a2ui_hub,
    code_team_render,
    code_team_run,
)
from api.main import CodeTeamRequest  # noqa: E402


def _routes():
    out = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None) or set()
        out.setdefault(path, set()).update(methods)
    return out


def test_routes_registered():
    """端点确实注册到 app.routes（证明 import 链完整、路由未被吞）。"""
    rs = _routes()
    assert "GET" in rs.get("/api/a2ui/hub", set())
    assert "GET" in rs.get("/api/a2ui/demo", set())
    assert "POST" in rs.get("/api/code_team/run", set())
    assert "POST" in rs.get("/api/code_team/render", set())
    assert "POST" in rs.get("/api/orchestrator/render", set())


def test_a2ui_hub_handler():
    """a2ui_hub() → 200 + text/html + 列出各可视化端点路径。"""
    resp = asyncio.run(a2ui_hub())
    assert resp.status_code == 200
    assert "text/html" in resp.media_type
    body = resp.body.decode("utf-8")
    assert "AOS" in body
    assert "/api/orchestrator/render" in body
    assert "/api/code_team/render" in body
    assert "/api/a2ui/demo" in body
    assert "a2ui-surface" in body  # 经 A2UI 渲染器，非裸 HTML


def test_a2ui_demo_handler():
    """a2ui_demo() → 200 + text/html + A2UI surface 容器。"""
    resp = asyncio.run(a2ui_demo())
    assert resp.status_code == 200
    assert "text/html" in resp.media_type
    assert "a2ui-surface" in resp.body.decode("utf-8")


def test_code_team_run_handler_heuristic():
    """code_team_run(计算器需求) → JSON + 诚实标注 llm_used + 真跑过质量门。"""
    data = asyncio.run(
        code_team_run(CodeTeamRequest(requirement="写一个计算器，支持加减乘除", lang="python"))
    )
    assert isinstance(data, dict)
    # 沙箱无真实 LLM → 诚实标注未走 LLM。
    assert data.get("llm_used") is False
    assert "files" in data and data["files"]
    assert "execution" in data
    assert data["execution"].get("ok") is True


def test_code_team_render_handler_heuristic():
    """code_team_render(计算器需求) → 200 + text/html A2UI 交付物。"""
    resp = asyncio.run(
        code_team_render(CodeTeamRequest(requirement="写一个计算器，支持加减乘除", lang="python"))
    )
    assert resp.status_code == 200
    assert "text/html" in resp.media_type
    body = resp.body.decode("utf-8")
    assert "a2ui-surface" in body
    assert ("计算器" in body) or ("calculator" in body)
