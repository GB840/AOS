"""ResilienceBus 熔断器增强单测（#11/#12 熔断区分收口验证）。

覆盖：
  * on_failure(error=None) 向后兼容（已有 test_breaker_state_machine 仍绿）
  * 429 限流 → 短冷却（5s），且不污染 5xx 退避计数
  * 5xx 上游故障 → 指数退避 base*2**n 封顶 300s
  * 普通错误 → 维持构造期默认冷却
  * on_outcome 把 error 透传给 on_failure（429 路径真生效）

诚实分级：②（代码+单测实证）。用假时钟消除真实 sleep。
"""

import sys
sys.path.insert(0, "D:/AOS/src")

from unittest import mock

from core.fabric.resilience_bus import ResilienceBus, _PerEngineBreaker


def _breaker(failure_threshold=3, cooldown=30.0):
    return _PerEngineBreaker("x", failure_threshold=failure_threshold,
                             cooldown=cooldown, success_threshold=2)


def test_on_failure_backward_compat_no_arg():
    """on_failure() 无参调用（旧测试契约）不报错。"""
    b = _breaker(failure_threshold=1)
    b.on_failure()  # 不应抛异常
    assert b.is_open is True


def test_429_short_cooldown():
    """429 限流 → 短冷却 5s，且 5xx 退避计数保持 0。"""
    fake = {"t": 1000.0}

    def fake_time():
        return fake["t"]

    with mock.patch("core.fabric.resilience_bus.time.time", side_effect=fake_time):
        b = _breaker(failure_threshold=1)
        b.on_failure("HTTP 429 rate limited")
        assert b.is_open is True
        assert b._cooldown == 5.0
        assert b._consecutive_5xx_trips == 0
        # 越过快冷却即转 half_open（允许重试）
        fake["t"] += 6.0
        assert b.state == "half_open"


def test_5xx_exponential_backoff():
    """5xx → 指数退避 30 → 60 → 120 → 240 → 300(封顶)。"""
    b = _breaker(failure_threshold=1)
    b.on_failure("status_code=503")
    assert b._cooldown == 30.0
    assert b._consecutive_5xx_trips == 1
    b.on_failure("500 Internal")
    assert b._cooldown == 60.0
    assert b._consecutive_5xx_trips == 2
    b.on_failure("502 Bad Gateway")
    assert b._cooldown == 120.0
    assert b._consecutive_5xx_trips == 3
    b.on_failure("503")
    assert b._cooldown == 240.0
    b.on_failure("504")
    assert b._cooldown == 300.0  # 封顶
    assert b._consecutive_5xx_trips == 5


def test_429_does_not_touch_5xx_counter():
    """429 不应增加 5xx 退避计数。"""
    b = _breaker(failure_threshold=1)
    b.on_failure("429 Too Many Requests")
    b.on_failure("429 Too Many Requests")
    assert b._consecutive_5xx_trips == 0
    assert b._cooldown == 5.0


def test_generic_error_keeps_default_cooldown():
    """普通错误（无 HTTP 状态码）→ 维持构造期默认冷却，不动态调整。"""
    b = _breaker(failure_threshold=1, cooldown=30.0)
    b.on_failure("connection refused")
    assert b._cooldown == 30.0
    assert b._consecutive_5xx_trips == 0


def test_recover_resets_5xx_counter():
    """恢复（on_success 关闭熔断）→ 退避计数清零，下次 5xx 从头算。"""
    b = _breaker(failure_threshold=1)
    b.on_failure("503")
    assert b._consecutive_5xx_trips == 1
    b.on_success()  # half_open → 未达 success 阈值，仍 open
    # 直接关闭：再 success 达阈值
    b.on_success()
    assert b.state == "closed"
    assert b._consecutive_5xx_trips == 0
    b.on_failure("503")
    assert b._consecutive_5xx_trips == 1
    assert b._cooldown == 30.0


def test_on_outcome_passes_error_429():
    """on_outcome 把 error 透传给熔断器 → 429 短冷却真生效。"""
    bus = ResilienceBus()
    for _ in range(3):
        bus.on_outcome("e", False, "HTTP 429 rate limited")
    assert bus.should_skip("e") is True
    br = bus._breakers["e"]
    assert br._cooldown == 5.0
    assert br._consecutive_5xx_trips == 0
