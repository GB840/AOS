"""resilience.guarded_import 分级超时 + prewarm 预热机制单测。

不依赖任何重型包（litellm/autogen），用 stdlib 模块与缺失模块验证逻辑，
确保「重型依赖导入慢/卡死」的修复不退化。
"""
import time

from core.fabric import resilience


def test_default_and_module_timeouts():
    # 分级超时表：重型依赖给足时间，避免被一刀切 dead
    assert resilience._DEFAULT_TIMEOUT == 20.0
    assert resilience._MODULE_TIMEOUTS["autogen"] == 180.0
    assert resilience._MODULE_TIMEOUTS["ag2"] == 180.0
    assert resilience._MODULE_TIMEOUTS["litellm"] == 30.0


def test_guarded_import_missing_returns_none():
    # 不存在的模块：超时后返回 None，绝不抛出异常/阻塞
    resilience.clear_caches()
    assert resilience.guarded_import("this_module_does_not_exist_xyz") is None


def test_prewarm_caches_module():
    # prewarm 后台 import 轻模块，结果缓存到 _PROBED
    resilience.clear_caches()
    resilience.prewarm(["json"])
    time.sleep(0.3)
    assert resilience._PROBED.get("json") is not None
    assert not resilience.is_warming("json")


def test_prewarm_idempotent():
    # 重复 prewarm 同模块不重复起线程
    resilience.clear_caches()
    resilience.prewarm(["json"])
    resilience.prewarm(["json"])
    assert resilience.is_warming("json") or resilience._PROBED.get("json") is not None


def test_clear_caches_clears_warming():
    resilience.clear_caches()
    assert not resilience.is_warming("json")
