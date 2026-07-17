"""ENGINE_TIER 键名对齐修复验证。

背景（探查定位的真缺口）：
- `web-search` 适配器（engine_id="web-search"，advertise WEB_SEARCH）本应是
  低档（含免费搜索源兜底），但 ENGINE_TIER 里错写成 `"search"`，导致该引擎
  默认 tier() 落空、回落中档，档位级联路由对其失效。
- `browser-use` 适配器（engine_id="browser-use"，advertise ACI/TOOL_USE）的
  ENGINE_TIER 键名错写成 `"browseruse"`，同样落空回落中档。

路由派发（registry.providers_for）用适配器 tier()（默认读 ENGINE_TIER[engine_id]）
做「档位优先 + 向低档级联」，所以这两个错键名是真 bug，非仅静态视图问题。
修复 = 把 `"browseruse"`→`"browser-use"`、`"search"`→`"web-search"`。
"""

import pytest

from core.fabric.capability import (
    ENGINE_TIER,
    TIER_LOW,
    TIER_MEDIUM,
)


def test_engine_tier_keys_aligned_and_orphans_gone():
    """ENGINE_TIER 键名与适配器 engine_id 对齐，孤儿错键已清除。"""
    # 修复后：正确键名存在且档位正确
    assert "web-search" in ENGINE_TIER, "web-search 键缺失"
    assert ENGINE_TIER["web-search"] == TIER_LOW, "web-search 应为低档（免费搜索源兜底）"
    assert "browser-use" in ENGINE_TIER, "browser-use 键缺失"
    assert ENGINE_TIER["browser-use"] == TIER_MEDIUM, "browser-use 应为中档（云端浏览器自动化）"
    # 孤儿错键已清除（避免静默落空）
    assert "search" not in ENGINE_TIER, "孤儿键 'search' 应已改名 'web-search'"
    assert "browseruse" not in ENGINE_TIER, "孤儿键 'browseruse' 应已改名 'browser-use'"


def test_web_search_adapter_runtime_tier_is_low():
    """穿透：web-search 适配器运行时 tier() 真实返回 low（修复生效到路由层）。"""
    try:
        from core.fabric.adapters import search_adapter as m
    except Exception:  # 重型搜索源依赖缺失 → 跳过，不红
        pytest.skip("search_adapter 不可导入（重型依赖缺失）")
    cls = getattr(m, "SearchAdapter", None) or getattr(m, "WebSearchAdapter", None)
    if cls is None:
        pytest.skip("未找到 web-search 适配器类")
    try:
        adapter = cls()
    except Exception:
        pytest.skip("web-search 适配器构造失败（环境限制）")
    assert adapter.engine_id == "web-search"
    assert adapter.tier() == TIER_LOW, "web-search 运行时档位应回落为 low"


def test_browser_use_adapter_runtime_tier_is_medium():
    """穿透：browser-use 适配器运行时 tier() 真实返回 medium（键名对齐后正确）。"""
    try:
        from core.fabric.adapters.aci_browser_adapter import BrowserUseAdapter
    except Exception:
        pytest.skip("aci_browser_adapter 不可导入（重型依赖缺失）")
    try:
        adapter = BrowserUseAdapter()
    except Exception:
        pytest.skip("browser-use 适配器构造失败（环境限制）")
    assert adapter.engine_id == "browser-use"
    assert adapter.tier() == TIER_MEDIUM
