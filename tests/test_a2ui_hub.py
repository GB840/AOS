"""A2UI 通用目录工厂 build_index_surface 测试。

覆盖：合法 surface / 含条目文本 / 文本转义（安全）/ 空条目不崩。
沙箱可跑、不依赖网络与重型适配器。
"""
from core.fabric import a2ui


def _entries():
    return [
        {"title": "编排流水线可视化", "method": "POST",
         "path": "/api/orchestrator/render", "desc": "把编排 trace 渲染成 A2UI 报告。"},
        {"title": "代码团队可视化", "method": "POST",
         "path": "/api/code_team/render", "desc": "代码团队结果转 A2UI 交付物。"},
    ]


def test_index_surface_is_valid():
    """产出的 surface 合法：validate_surface 返回空错误列表。"""
    surface = a2ui.build_index_surface("目录", _entries(), subtitle="副标题")
    assert isinstance(surface, dict)
    assert a2ui.validate_surface(surface) == []
    # root 是标准字符串 id 且在 components 内
    assert isinstance(surface["root"], str)
    assert surface["root"] in surface["components"]


def test_index_surface_renders_entry_text_and_path():
    """渲染 HTML 含每个条目的标题与路径。"""
    html = a2ui.render_html(a2ui.build_index_surface("目录", _entries()), standalone=True)
    assert "a2ui-surface" in html
    assert "编排流水线可视化" in html
    assert "/api/orchestrator/render" in html
    assert "代码团队可视化" in html


def test_index_surface_escapes_html():
    """条目文本经 lit() 转义，不注入原始 HTML（跨信任边界安全）。"""
    entries = [{"title": "<b>x</b>", "method": "GET",
                "path": "/p", "desc": "<script>alert(1)</script>"}]
    html = a2ui.render_html(a2ui.build_index_surface("t", entries), standalone=True)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_index_surface_empty_entries():
    """空条目也能产出合法 surface 且渲染不崩。"""
    surface = a2ui.build_index_surface("空目录", [])
    assert a2ui.validate_surface(surface) == []
    html = a2ui.render_html(surface, standalone=True)
    assert "无可用面板" in html
