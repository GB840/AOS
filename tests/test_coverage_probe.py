"""#558 覆盖率实测探针：仅导入 numpy-free 的三个核心模块
（trace_store / memory_distiller / resilience_bus），不碰 FabricHub，
从而绕开 numpy 2.x 与 coverage.py 的「同进程二次加载」不兼容。

本文件用真实调用把这三个模块的关键方法都跑到，使 coverage 能给出
真实行覆盖率数字（不造假、不凑 50% 门槛）。
"""
import os
import sys
import types

# 工作区绕过：numpy 2.x 的 C 扩展在 coverage.py 追踪器下会「同进程二次加载」
# 而本项目的 core.fabric 包 __init__ 在导入时即拉起 route_predictor → numpy，
# 导致 coverage 无法采集任何 core.fabric 子模块。此 stub 仅让导入链路通过
# （探针不实例化 RoutePredictor，故无需真实 numpy API）。生产代码仍用真实 numpy。
# 仅在 coverage 激活时注入，避免污染普通 pytest 运行（无追踪器时真实 numpy 正常）。
if "coverage" in sys.modules and "numpy" not in sys.modules:
    sys.modules["numpy"] = types.ModuleType("numpy")

sys.path.insert(0, "src")

from core.fabric.adapter import InvokeResult  # noqa: E402
from core.fabric.resilience_bus import (  # noqa: E402
    ResilienceBus, _PerEngineBreaker)
from core.fabric.trace_store import TaskTraceStore, TracedRoute  # noqa: E402
from kernel.memory_distiller import MemoryDistiller  # noqa: E402


def test_probe_trace_store_and_traced_route(tmp_path):
    store = TaskTraceStore(traces_dir=str(tmp_path))
    store.begin("t1", "搜索任务")
    store.add_step("t1", "web.search", "good", True, None, 1.5)
    store.add_step("t1", "web.process", "bad", False, "HTTP 500", 2.5)
    p = store.finish("t1", ok=False)
    assert p and os.path.exists(p)

    # 轮转路径：制造多文件触发 _enforce_rotation 分支
    for i in range(3):
        s = TaskTraceStore(traces_dir=str(tmp_path))
        s.begin(f"r{i}", "g")
        s.finish(f"r{i}", True)

    # TracedRoute 正常路径 + 异常路径（异常也记失败 trace）
    calls = {"n": 0}

    def _hub_ok(cap, payload):
        calls["n"] += 1
        return InvokeResult(ok=True, data={"x": 1}, engine_id="good")

    def _hub_boom(cap, payload):
        raise RuntimeError("引擎崩了")

    store.begin("t2", "g")
    tr = TracedRoute(_hub_ok, store, "t2")
    r = tr("web.search", {"q": "x"})
    assert r.ok and calls["n"] == 1
    tr2 = TracedRoute(_hub_boom, store, "t2")
    try:
        tr2("web.search", {"q": "x"})
    except RuntimeError:
        pass
    store.finish("t2", True)


def test_probe_distiller_scan_and_lifecycle_noops(tmp_path):
    store = TaskTraceStore(traces_dir=str(tmp_path))
    store.begin("d1", "蒸馏任务")
    store.add_step("d1", "web.search", "good", True, None, 1.0)
    store.add_step("d1", "web.process", "bad", False, "HTTP 500", 2.0)
    store.finish("d1", False)

    d = MemoryDistiller(trace_dirs=[str(tmp_path)], interval_seconds=1)
    rep = d.scan_once()
    assert rep.scanned_files >= 1
    assert rep.new_items >= 1
    # 无 lifecycle 时的空查询路径
    assert d.recall_memories() == []
    assert d.lifecycle_report() is None
    assert d.lifecycle_prune() is None
    # 重复扫描不重复提炼（指纹防重）
    rep2 = d.scan_once()
    assert rep2.new_items == 0


def test_probe_resilience_bus_full_loop():
    rb = ResilienceBus()
    assert rb.should_skip("x") is False
    assert rb._total_failures == 0
    for _ in range(3):
        rb.on_outcome("x", False, "HTTP 503")
    assert rb.should_skip("x") is True
    assert rb._circuit_trips >= 1
    assert rb._total_failures >= 3
    # 成功回灌 → 关闭熔断
    rb.on_outcome("x", True)
    assert rb.should_skip("x") is False
    assert rb._total_success >= 1


def test_probe_breaker_cooldown_matrix():
    # 429 短冷却
    b429 = _PerEngineBreaker("a")
    for _ in range(3):
        b429.on_failure("HTTP 429 rate limited")
    assert b429._cooldown == 5.0
    # 5xx 指数退避：每次失败都 +1 指数（熔断后持续失败则翻倍）+ 封顶
    b5 = _PerEngineBreaker("b")
    for _ in range(3):
        b5.on_failure("HTTP 503")
    assert b5._cooldown == 30.0       # 第 1 次熔断：base
    b5.on_failure("HTTP 503")         # 第 4 次失败 → 60
    assert b5._cooldown == 60.0
    for _ in range(20):
        b5.on_failure("HTTP 503")
    assert b5._cooldown == 300.0      # 封顶 300s
    # 成功恢复 → 状态关闭
    b5.on_success()
    assert b5.state == "closed"
    # 无状态码 → 维持默认冷却 30s
    bdef = _PerEngineBreaker("c")
    for _ in range(3):
        bdef.on_failure("generic blip")
    assert bdef._cooldown == 30.0
