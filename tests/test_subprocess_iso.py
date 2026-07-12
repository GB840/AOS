"""子进程隔离层功能测试（B 路线 PoC）。

注意：这些是「功能正确性」断言（spawn/health/invoke/恢复），不绑定机器相关的
性能闸门——性能闸门在 scripts/subprocess_iso_probe.py 里按真实硬件判定。
每个测试都会真实拉起 / 杀死一个子进程，验证隔离语义确实成立。
"""
from __future__ import annotations

import sys

sys.path.insert(0, "D:/AOS/src")

import os

import pytest

from kernel.isolation.subprocess_iso import SubprocessIsolationLayer

# 测试在 CI/沙箱跑：这些环境通常不支持 Named Pipe，默认退化为 tcp loopback。
# 真实宿主上运行可设 AOS_ISO_TRANSPORT=pipe 走 Named Pipe。
TRANSPORT = os.environ.get("AOS_ISO_TRANSPORT", "tcp")


@pytest.fixture
def layer():
    l = SubprocessIsolationLayer(engine_id="test_iso", transport=TRANSPORT)
    l.start()
    yield l
    l.stop()


def test_spawn_and_health(layer: SubprocessIsolationLayer):
    assert layer.health() is True
    assert layer.spawn_ms is not None and layer.spawn_ms > 0


def test_invoke_roundtrip(layer: SubprocessIsolationLayer):
    res = layer.invoke("bench.ping", {"k": "v"})
    assert isinstance(res, dict)
    assert res.get("ok") is True
    assert res["data"]["echo"]["k"] == "v"
    # RTT 已被记录
    assert layer.rtt_us is not None and layer.rtt_us > 0


def test_kill_and_recover_restores_service(layer: SubprocessIsolationLayer):
    rec = layer.kill_and_recover()
    assert layer.health() is True
    assert rec > 0
    res = layer.invoke("bench.ping", {"k": 2})
    assert isinstance(res, dict)
    assert res.get("ok") is True
    assert res["data"]["echo"]["k"] == 2
