"""A2UI（v0.9）协议模块测试：构建、安全渲染、编排桥接、消息往返。

不依赖网络/外部服务，纯标准库即可跑。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import core.fabric.a2ui as a2ui


def test_demo_surface_renders_and_is_safe():
    surf = a2ui._demo_surface()
    assert a2ui.validate_surface(surf) == []
    html = a2ui.render_html(surf, standalone=False)
    assert "a2ui-surface" in html
    # 无脚本注入
    assert "<script>" not in html


def test_xss_text_is_escaped():
    b = a2ui.A2UIBuilder("x")
    b.add("t", a2ui.text("<img src=x onerror=alert(1)>", variant="body"))
    b.add("root", a2ui.column(["t"]))
    b.root("root")
    h = a2ui.render_html(b.surface())
    assert "&lt;img" in h
    assert "<img src=x" not in h


def test_builder_rejects_unknown_component():
    b = a2ui.A2UIBuilder("y")
    try:
        b.add("bad", {"component": "Hack", "text": a2ui.lit("x")})
        assert False, "应拒绝未知组件"
    except ValueError:
        pass


def test_renderer_rejects_unknown_component_no_live_element():
    # 模拟外部/ag2 传入的未受信 surface：渲染期也应拒（无活元素）
    raw = {"surfaceId": "y", "root": "root",
           "components": {"root": {"component": "Hack", "text": a2ui.lit("x")}}}
    h = a2ui.render_html(raw)
    assert "a2ui-text" not in h and "a2ui-card" not in h
    # 仅以转义的校验错误呈现，不渲染该组件
    assert "a2ui-error" in h


def test_dangerous_url_blocked():
    b = a2ui.A2UIBuilder("z")
    b.add("i", a2ui.image(a2ui.lit("javascript:alert(1)")))
    b.add("root", a2ui.column(["i"]))
    b.root("root")
    assert "被拦截" in a2ui.render_html(b.surface())


def test_https_url_allowed():
    b = a2ui.A2UIBuilder("w")
    b.add("i", a2ui.image(a2ui.lit("https://x.com/a.png")))
    b.add("root", a2ui.column(["i"]))
    b.root("root")
    h = a2ui.render_html(b.surface())
    assert "src='https://x.com/a.png'" in h


def test_data_model_path_binding():
    b = a2ui.A2UIBuilder("d")
    b.add("t", a2ui.text(a2ui.ref("/user/name")))
    b.add("root", a2ui.column(["t"]))
    b.root("root")
    b.set_data("/user/name", "Alice")
    h = a2ui.render_html(b.surface())
    assert "Alice" in h


def test_build_a2ui_report_produces_valid_surface():
    trace = [
        {"step": 0, "capability": "bench.ping", "ok": True, "out": "pong"},
        {"step": 1, "capability": "x", "ok": False, "error": "boom"},
    ]
    rep = a2ui.build_a2ui_report(trace, ok_steps=1, failed_steps=1, final={"k": "v"})
    assert a2ui.validate_surface(rep) == [], a2ui.validate_surface(rep)
    html = a2ui.render_html(rep)
    assert "✓" in html and "✗" in html
    assert "boom" in html


def test_messages_roundtrip_to_surface():
    b = a2ui.A2UIBuilder("m")
    b.add("t", a2ui.text(a2ui.lit("hi")))
    b.add("root", a2ui.column(["t"]))
    b.root("root")
    msgs = b.messages()
    surf = a2ui._messages_to_surface(msgs)
    assert a2ui.validate_surface(surf) == [], a2ui.validate_surface(surf)
    assert a2ui.render_html(surf).startswith("<div class='a2ui-surface'")


def test_render_a2ui_accepts_messages_payload():
    b = a2ui.A2UIBuilder("m")
    b.add("t", a2ui.text(a2ui.lit("hi")))
    b.add("root", a2ui.column(["t"]))
    b.root("root")
    html = a2ui.render_a2ui({"messages": b.messages()}, standalone=False)
    assert "a2ui-surface" in html


def test_orchestration_result_to_a2ui_bridge():
    from core.fabric.adapter import InvokeResult
    from kernel.plugins.orchestration_chiplet import orchestration_result_to_a2ui

    # 成功结果含 trace -> 产出合法 surface
    ok = InvokeResult(ok=True, data={
        "ok_steps": 1, "failed_steps": 0,
        "final": {"answer": 42},
        "trace": [{"step": 0, "capability": "bench.ping", "ok": True, "out": "pong"}],
    })
    surf = orchestration_result_to_a2ui(ok)
    assert surf is not None
    assert a2ui.validate_surface(surf) == [], a2ui.validate_surface(surf)
    assert "42" in a2ui.render_html(surf)

    # 失败结果 -> 不伪造，返回 None
    assert orchestration_result_to_a2ui(InvokeResult(ok=False, error="x")) is None
    # 缺 trace -> 返回 None
    assert orchestration_result_to_a2ui(InvokeResult(ok=True, data={})) is None
