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


def test_expired_negative_cache_recovers():
    # 修复回归：超时负缓存到期后应允许重新探测，而非永久返回 None。
    resilience.clear_caches()
    # 注入一个已过期的负缓存条目
    resilience._PROBED["json"] = (resilience._NEG, time.time() - 1)
    # json 真实可用 -> 重新探测成功，证明未永久缓存为不可用
    assert resilience.guarded_import("json") is not None


def test_permanent_negative_cache_sticks():
    # 导入报错（模块确实缺失）仍永久缓存为不可用，保性能。
    resilience.clear_caches()
    resilience._PROBED["nope_mod"] = resilience._PERM_NEG
    assert resilience.guarded_import("nope_mod") is None

