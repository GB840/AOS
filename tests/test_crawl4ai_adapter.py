"""Crawl4AIAdapter 测试：能力注册、health 真实探测、缺依赖优雅降级、hub 路由。

不真实联网爬取（除非 crawl4ai 已安装且有网络），重点验证：
1. 能力注册：advertise_capabilities 含 WEB_CRAWL
2. health 真实探测：crawl4ai 装了 True，没装 False（绝不谎报 live）
3. 缺依赖优雅降级：invoke 返回 ok=False + 明确错误，不崩溃
4. hub 注册：FabricHub(adapters=(Crawl4AIAdapter,)) 按健康状态正确路由/忽略
"""
from __future__ import annotations

import sys

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import crawl4ai_adapter as m


def _crawl4ai_installed() -> bool:
    return "crawl4ai" in sys.modules or _try_import()


def _try_import() -> bool:
    try:
        import crawl4ai  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


CRAWL4AI_OK = _crawl4ai_installed()


def test_crawl4ai_adapter_advertises_web_crawl():
    a = m.Crawl4AIAdapter()
    assert Capability.WEB_CRAWL in a.advertise_capabilities()
    assert a.engine_id == "web-crawl"


def test_crawl4ai_adapter_health_reflects_dependency():
    # health 必须基于真实可导入性，不硬编码
    a = m.Crawl4AIAdapter()
    assert a.health() is CRAWL4AI_OK


def test_crawl4ai_adapter_invoke_missing_url():
    res = m.Crawl4AIAdapter().invoke(
        InvokeRequest(capability="web.crawl", payload={})
    )
    assert res.ok is False
    assert "URL" in res.error


def test_crawl4ai_adapter_invoke_graceful_when_uninstalled():
    # crawl4ai 未安装时：绝不崩溃，明确告知需安装
    if CRAWL4AI_OK:
        pytest.skip("crawl4ai 已安装，跳过未安装降级用例")
    res = m.Crawl4AIAdapter().invoke(
        InvokeRequest(capability="web.crawl", payload={"url": "https://example.com"})
    )
    assert res.ok is False
    assert "crawl4ai" in res.error.lower()


def test_fabric_hub_registers_or_skips_crawl4ai():
    # 隔离测试：只装 Crawl4AIAdapter，验证 hub 路由与其健康状态一致
    from kernel.plugins.fabric_hub import FabricHub

    hub = FabricHub(adapters=(m.Crawl4AIAdapter,))
    if CRAWL4AI_OK:
        assert hub.resolve_engine("web.crawl") == "web-crawl"
    else:
        # 未安装 → health=False → 路由层应忽略（不谎报可达）
        assert hub.resolve_engine("web.crawl") is None


@pytest.mark.skipif(not CRAWL4AI_OK, reason="需先 pip install crawl4ai")
def test_crawl4ai_adapter_real_crawl():
    # 真机爬取（需 crawl4ai + 网络 + chromium）：验证端到端产出 Markdown
    res = m.Crawl4AIAdapter().invoke(
        InvokeRequest(capability="web.crawl", payload={"url": "https://example.com"})
    )
    assert res.ok is True
    assert "markdown" in res.data
    assert len(res.data["markdown"]) > 0
    assert res.data["url"] == "https://example.com"
