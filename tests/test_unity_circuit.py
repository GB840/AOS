"""测试CircuitBreaker半开状态逻辑（O5修复验证）"""
import pytest
import time
from kernel.immunity import CircuitBreaker, CircuitBreakerOpenError


def test_circuit_breaker_half_open_requires_consecutive_success():
    """测试半开状态连续3次成功才关闭熔断器"""
    cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=0.1, success_threshold=3)

    # 触发3次失败，打开熔断器
    for _ in range(3):
        try:
            with cb:
                raise Exception("test failure")
        except Exception:
            pass

    assert cb.state == "open"

    # 等待冷却时间，进入半开状态
    time.sleep(0.2)

    # 第1次成功，熔断器仍为半开状态
    with cb:
        pass
    assert cb.state == "half_open"

    # 第2次成功，熔断器仍为半开状态
    with cb:
        pass
    assert cb.state == "half_open"

    # 第3次成功，熔断器关闭
    with cb:
        pass
    assert cb.state == "closed"


def test_circuit_breaker_half_open_failure_resets_count():
    """测试半开状态中间失败重置计数"""
    cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=0.1, success_threshold=3)

    # 触发3次失败，打开熔断器
    for _ in range(3):
        try:
            with cb:
                raise Exception("test failure")
        except Exception:
            pass

    assert cb.state == "open"

    # 等待冷却时间，进入半开状态
    time.sleep(0.2)

    # 第1次成功
    with cb:
        pass
    assert cb.state == "half_open"

    # 第2次失败，重置计数
    try:
        with cb:
            raise Exception("test failure")
    except Exception:
        pass
    assert cb.state == "open"

    # 等待冷却时间，再次进入半开状态
    time.sleep(0.2)

    # 第1次成功
    with cb:
        pass
    assert cb.state == "half_open"

    # 第2次成功
    with cb:
        pass
    assert cb.state == "half_open"

    # 第3次成功，熔断器关闭
    with cb:
        pass
    assert cb.state == "closed"
