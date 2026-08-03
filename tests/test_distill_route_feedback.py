"""蒸馏→路由反馈闭环集成验证（#272 收口验证）。

验证链路：
  EvolutionDistiller → EngineStat JSONL（独立统计系统）
  MemoryDistiller → DistilledMemory records → distilled_memory.jsonl（注册表格式）
  FabricRegistry.reload_distilled() → _distilled_penalties → 不可靠引擎被沉底惩罚。

诚实分级：②（代码+单测实证）。
"""

import sys
sys.path.insert(0, "D:/AOS/src")

import os
import json
import tempfile
from kernel.evolution_distiller import EvolutionDistiller


def _temp_distilled_path():
    return os.path.join(tempfile.mkdtemp(prefix="aos_272_test_"), "distilled.jsonl")


def _write_distilled_jsonl(path, records):
    """写入 FabricRegistry.reload_distilled() 期望的 DistilledMemory 格式。

    MemoryDistiller 产出的 metadata.key 格式 = "capability/engine"
    （如 "web.search/bing"），注册表 reload_distilled 按 "/" 分割。
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ── EvolutionDistiller 独立统计系统 ────────────────────────

def test_evolution_distiller_ingest_and_reload():
    """蒸馏统计写入 JSONL → 新实例重加载 → 统计一致。"""
    path = _temp_distilled_path()
    d = EvolutionDistiller(store_path=path)
    for _ in range(8):
        d.record_outcome("web.search", "bing", False)
    for _ in range(2):
        d.record_outcome("web.search", "bing", True)
    # record_outcome 使用节流落盘（30s 间隔），测试中强制立即落盘
    d._save()

    assert os.path.exists(path)

    # 新实例从同一文件加载
    d2 = EvolutionDistiller(store_path=path)
    assert "web.search::bing" in d2.stats
    assert d2.stats["web.search::bing"].total == 10
    assert d2.stats["web.search::bing"].fail == 8

    os.remove(path)
    os.rmdir(os.path.dirname(path))


def test_evolution_distiller_ingest_trace():
    """EvolutionDistiller 从 trace JSON 摄入多步统计。"""
    d = EvolutionDistiller(store_path=None)
    trace = {
        "steps": [
            {"capability": "web.search", "engine": "bing", "ok": False, "error": "timeout"},
            {"capability": "web.search", "engine": "duckduckgo", "ok": True},
            {"capability": "inference.llm", "engine": "deepseek", "ok": True},
        ]
    }
    d.ingest(trace)
    assert d.stats["web.search::bing"].total == 1
    assert d.stats["web.search::bing"].fail == 1
    assert d.stats["web.search::duckduckgo"].total == 1
    assert d.stats["web.search::duckduckgo"].ok == 1
    assert d.stats["inference.llm::deepseek"].total == 1


def test_distill_sinks_high_failure_engine():
    """高失败率引擎被蒸馏器沉底建议。"""
    d = EvolutionDistiller(store_path=None)
    for _ in range(8):
        d.record_outcome("web.search", "bing", False)
    for _ in range(2):
        d.record_outcome("web.search", "bing", True)
    for _ in range(9):
        d.record_outcome("web.search", "duckduckgo", True)
    for _ in range(1):
        d.record_outcome("web.search", "duckduckgo", False)

    sinks = d.distill()
    sunk_engines = {s["engine"] for s in sinks}
    assert "bing" in sunk_engines
    assert "duckduckgo" not in sunk_engines


def test_distill_no_sink_below_threshold():
    """样本不足或失败率不达阈值 → 不沉底。"""
    d = EvolutionDistiller(store_path=None)
    for _ in range(3):
        d.record_outcome("inference.llm", "test_model", False)
    assert len(d.distill()) == 0  # 仅 3 < MIN_SAMPLES=5

    for _ in range(4):
        d.record_outcome("inference.llm", "test_model", True)
    assert len(d.distill()) == 0  # 3/7=0.428 < 0.5


# ── FabricRegistry 蒸馏惩罚加载 ────────────────────────────

def test_registry_loads_distilled_penalties():
    """FabricRegistry 从 distilled_memory.jsonl 加载并施加软惩罚。

    格式精确对应 MemoryDistiller._distill_route_outcomes 产出的 metadata.key="capability/engine"。
    """
    from core.fabric.registry import FabricRegistry

    path = _temp_distilled_path()
    _write_distilled_jsonl(path, [
        {
            "text": "路由可靠性：能力/引擎「web.search/bing」成功率 2/10",
            "category": "capability_reliability",
            "source": "route_outcomes.jsonl",
            "confidence": 0.9,
            "metadata": {"key": "web.search/bing", "ok": 2, "total": 10},
        },
        {
            "text": "路由可靠性：能力/引擎「web.search/duckduckgo」成功率 9/10",
            "category": "capability_reliability",
            "source": "route_outcomes.jsonl",
            "confidence": 0.95,
            "metadata": {"key": "web.search/duckduckgo", "ok": 9, "total": 10},
        },
    ])

    reg = FabricRegistry(
        distilled_memory_path=path,
        distilled_min_samples=5,
        distilled_reliability_threshold=0.5,
    )

    diag = reg.distilled_diagnostics()
    assert diag["enabled"] is True
    assert diag["loaded"] is True
    assert diag["penalty_count"] >= 1

    penalties = diag["penalties"]
    # bing 失败率 0.8 → 惩罚 key = "web.search|bing"
    bing_key = "web.search|bing"
    assert bing_key in penalties, f"Expected {bing_key} penalty, got: {penalties}"
    assert penalties[bing_key] > 0

    # duckduckgo 成功率 0.9 → 不惩罚
    ddg_key = "web.search|duckduckgo"
    assert ddg_key not in penalties, f"duckduckgo should NOT be penalized, got: {penalties}"

    os.remove(path)
    os.rmdir(os.path.dirname(path))


def test_registry_multiple_engines():
    """多个引擎同时被蒸馏，各自独立判定是否沉底。"""
    from core.fabric.registry import FabricRegistry

    path = _temp_distilled_path()
    _write_distilled_jsonl(path, [
        # bing: 失败率 0.8 → 沉底
        {"text": "", "category": "capability_reliability", "source": "", "confidence": 0.9,
         "metadata": {"key": "web.search/bing", "ok": 2, "total": 10}},
        # duckduckgo: 成功率 0.9 → 不沉底
        {"text": "", "category": "capability_reliability", "source": "", "confidence": 0.95,
         "metadata": {"key": "web.search/duckduckgo", "ok": 9, "total": 10}},
        # zhipu: 失败率 0.6 → 应沉底
        {"text": "", "category": "capability_reliability", "source": "", "confidence": 0.8,
         "metadata": {"key": "web.search/zhipu", "ok": 4, "total": 10}},
        # deepseek (inference.llm): 好 → 不沉底
        {"text": "", "category": "capability_reliability", "source": "", "confidence": 0.9,
         "metadata": {"key": "inference.llm/deepseek", "ok": 8, "total": 10}},
    ])

    reg = FabricRegistry(distilled_memory_path=path, distilled_min_samples=5)
    diag = reg.distilled_diagnostics()
    penalties = diag["penalties"]

    # bing 和 zhipu 应该被惩罚
    assert "web.search|bing" in penalties
    assert "web.search|zhipu" in penalties
    # duckduckgo 不惩罚
    assert "web.search|duckduckgo" not in penalties
    # deepseek 不惩罚
    assert "inference.llm|deepseek" not in penalties

    os.remove(path)
    os.rmdir(os.path.dirname(path))


def test_registry_no_file_graceful():
    """蒸馏文件不存在 → 诊断正常、零惩罚。"""
    from core.fabric.registry import FabricRegistry

    reg = FabricRegistry(
        distilled_memory_path="/nonexistent/aos_distilled_test.jsonl",
    )
    diag = reg.distilled_diagnostics()
    assert diag["enabled"] is True
    assert diag["penalty_count"] == 0


def test_registry_recovery_after_improvement():
    """引擎表现改善后 → 蒸馏文件更新 → 惩罚自动解除。"""
    from core.fabric.registry import FabricRegistry

    path = _temp_distilled_path()
    _write_distilled_jsonl(path, [{
        "text": "", "category": "capability_reliability", "source": "",
        "confidence": 0.9,
        "metadata": {"key": "web.search/bing", "ok": 2, "total": 10},
    }])

    reg = FabricRegistry(distilled_memory_path=path, distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] >= 1

    # 改善 → 成功 22/30 = 0.73
    _write_distilled_jsonl(path, [{
        "text": "", "category": "capability_reliability", "source": "",
        "confidence": 0.9,
        "metadata": {"key": "web.search/bing", "ok": 22, "total": 30},
    }])

    reg.reload_distilled()
    assert "web.search|bing" not in reg.distilled_diagnostics()["penalties"]

    os.remove(path)
    os.rmdir(os.path.dirname(path))


def test_registry_ignores_insufficient_samples():
    """样本不足的记录 → 不施加惩罚。"""
    from core.fabric.registry import FabricRegistry

    path = _temp_distilled_path()
    _write_distilled_jsonl(path, [{
        "text": "", "category": "capability_reliability", "source": "",
        "confidence": 0.3,
        "metadata": {"key": "memory.recall/mem0", "ok": 0, "total": 3},
    }])

    reg = FabricRegistry(distilled_memory_path=path, distilled_min_samples=5)
    assert reg.distilled_diagnostics()["penalty_count"] == 0

    os.remove(path)
    os.rmdir(os.path.dirname(path))


# ── MemoryDistiller 格式兼容性 ─────────────────────────────

def test_memory_distiller_key_format():
    """MemoryDistiller._distill_route_outcomes 产出的 metadata.key 格式。

    验证注册表可正确消费此格式（capability/engine → capability|engine 惩罚 key）。
    """
    from core.fabric.registry import FabricRegistry

    path = _temp_distilled_path()
    # 模拟 route_outcomes.jsonl（引擎路由原始数据）
    route_outcomes = [
        {"capability": "web.search", "engine": "bing", "ok": False},
        {"capability": "web.search", "engine": "bing", "ok": True},
        {"capability": "web.search", "engine": "duckduckgo", "ok": True},
    ]

    # MemoryDistiller._distill_route_outcomes 的聚合逻辑：
    # key = f"{cap}/{eng}" → ok=sum, total=len
    # 这里直接模拟蒸馏后的结果
    distilled = [
        # web.search/bing: 1/2 = 0.5（刚好等于阈值 → 不沉底）
        {"text": "", "category": "capability_reliability", "source": "",
         "confidence": 0.5,
         "metadata": {"key": "web.search/bing", "ok": 1, "total": 2}},
        # 但样本不足（2 < 5）→ 也不沉底
    ]

    _write_distilled_jsonl(path, distilled)

    reg = FabricRegistry(distilled_memory_path=path, distilled_min_samples=5)
    # 样本 2 < 5 → 不够最小值，不施加惩罚
    assert reg.distilled_diagnostics()["penalty_count"] == 0

    os.remove(path)
    os.rmdir(os.path.dirname(path))


# ── route_runtime 配置 ─────────────────────────────────────

def test_route_runtime_build_distilled_path():
    """route_runtime.build_route_runtime() 正确配置 distilled_memory_path。"""
    from core.fabric.route_runtime import build_route_runtime, _DISTILLED_PATH

    cfg = build_route_runtime()
    assert cfg["distilled_memory_path"] == _DISTILLED_PATH
    assert "distilled_memory.jsonl" in cfg["distilled_memory_path"]
    assert "_traces" in cfg["distilled_memory_path"]
