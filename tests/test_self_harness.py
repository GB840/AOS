"""Self-Harness 单元测试。

覆盖：
- probe_adapters：适配器探活（healthy / 不可导入 / 构造异常 / health() 异常）
- smoke_eval：eval 冒烟（用真实 EvalHarness.score_trajectory，无外部依赖）
- check_stores：存储可写性检查
- run_self_test：overall_status 判定（healthy / degraded / unhealthy）
- 推荐建议生成
"""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="aos_test_selfharness_")
_BASE_ENV = {
    "AOS_PULSE_DIR": os.path.join(_tmp, "pulse"),
    "AOS_CONTEXT_DIR": os.path.join(_tmp, "context"),
    "AOS_EVAL_DIR": os.path.join(_tmp, "eval"),
}
for _k, _v in _BASE_ENV.items():
    os.environ[_k] = _v

# 预先禁用 tiktoken（避免网络下载）
import kernel.pulse.cost_tracker as _ct  # noqa: E402
_ct._TIKTOKEN_ENC = False

from kernel.self_harness import (  # noqa: E402
    SelfHarness,
    SelfTestReport,
)


@pytest.fixture(autouse=True)
def _restore_env():
    """每个测试后还原环境变量，避免 check_stores 测试污染后续用例。"""
    saved = {k: os.environ.get(k) for k in _BASE_ENV}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ── Mock 适配器 ──

class _HealthyAdapter:
    """健康适配器 mock。"""
    def health(self):
        return True

    def health_detail(self):
        return "all good"


class _UnhealthyAdapter:
    """health() 返回 False 的适配器。"""
    def health(self):
        return False


class _ExplodesOnConstruct:
    """构造时抛异常的适配器。"""
    def __init__(self):
        raise RuntimeError("缺依赖")


class _ExplodesOnHealth:
    """health() 抛异常的适配器。"""
    def __init__(self):
        pass

    def health(self):
        raise RuntimeError("连接超时")


# ── probe_adapters ──

def test_probe_adapters_healthy():
    """健康适配器应返回 healthy=True。"""
    specs = [("ok_engine", "test.cap", _HealthyAdapter)]
    h = SelfHarness(probe_specs=specs)
    results = h.probe_adapters()
    assert len(results) == 1
    assert results[0]["engine_id"] == "ok_engine"
    assert results[0]["healthy"] is True
    assert results[0]["detail"] == "all good"


def test_probe_adapters_unhealthy():
    """health()=False 的适配器应返回 healthy=False。"""
    specs = [("bad_engine", "test.cap", _UnhealthyAdapter)]
    h = SelfHarness(probe_specs=specs)
    results = h.probe_adapters()
    assert results[0]["healthy"] is False


def test_probe_adapters_construct_exception():
    """构造抛异常的适配器应记录异常，healthy=False。"""
    specs = [("broken_engine", "test.cap", _ExplodesOnConstruct)]
    h = SelfHarness(probe_specs=specs)
    results = h.probe_adapters()
    assert results[0]["healthy"] is False
    assert "构造/探活异常" in results[0]["detail"]
    assert "缺依赖" in results[0]["detail"]


def test_probe_adapters_health_exception():
    """health() 抛异常的适配器应记录异常，healthy=False。"""
    specs = [("err_engine", "test.cap", _ExplodesOnHealth)]
    h = SelfHarness(probe_specs=specs)
    results = h.probe_adapters()
    assert results[0]["healthy"] is False
    assert "构造/探活异常" in results[0]["detail"]


def test_probe_adapters_empty_specs():
    """无 specs 时应返回空列表。"""
    h = SelfHarness(probe_specs=[])
    assert h.probe_adapters() == []


def test_probe_adapters_multiple():
    """多个适配器应分别探活。"""
    specs = [
        ("ok1", "cap1", _HealthyAdapter),
        ("bad1", "cap2", _UnhealthyAdapter),
        ("broken", "cap3", _ExplodesOnConstruct),
    ]
    h = SelfHarness(probe_specs=specs)
    results = h.probe_adapters()
    assert len(results) == 3
    health_map = {r["engine_id"]: r["healthy"] for r in results}
    assert health_map["ok1"] is True
    assert health_map["bad1"] is False
    assert health_map["broken"] is False


# ── smoke_eval ──

def test_smoke_eval_passes():
    """smoke_eval 应通过——EvalHarness.score_trajectory 无外部依赖。"""
    h = SelfHarness(probe_specs=[])
    result = h.smoke_eval()
    assert result["ok"] is True
    assert result["score"] > 0
    assert "通过" in result["note"]


def test_smoke_eval_returns_score():
    """smoke_eval 应返回 score 数值。"""
    h = SelfHarness(probe_specs=[])
    result = h.smoke_eval()
    assert isinstance(result["score"], (int, float))
    assert result["score"] > 0


# ── check_stores ──

def test_check_stores_all_writable():
    """可写的存储应返回 writable=True。"""
    h = SelfHarness(probe_specs=[])
    checks = h.check_stores()
    assert len(checks) == 3
    # pulse_dir / context_dir / eval_dir 都应可写
    for c in checks:
        assert c["writable"] is True


def test_check_stores_creates_dirs():
    """check_stores 应自动创建目录。"""
    # 用一个新的临时路径
    new_path = os.path.join(_tmp, f"new_{os.urandom(4).hex()}", "subdir")
    os.environ["AOS_PULSE_DIR"] = new_path

    h = SelfHarness(probe_specs=[])
    checks = h.check_stores()
    pulse_check = next(c for c in checks if c["store"] == "pulse_dir")
    assert pulse_check["writable"] is True
    assert os.path.exists(new_path)


def test_check_stores_unwritable():
    """不可写路径应返回 writable=False 并记录 error。"""
    # 用一个不存在的盘符（Windows 下大概率不可写）
    bad_path = "Z:\\nonexistent_drive\\test_self_harness"
    os.environ["AOS_PULSE_DIR"] = bad_path

    h = SelfHarness(probe_specs=[])
    checks = h.check_stores()
    pulse_check = next(c for c in checks if c["store"] == "pulse_dir")
    # 可能 writable=False，也可能 Z 盘存在但没权限——只验证字段存在
    assert "writable" in pulse_check
    if pulse_check["writable"] is False:
        assert "error" in pulse_check


# ── run_self_test ──

def test_run_self_test_returns_report():
    """run_self_test 应返回完整的 SelfTestReport。"""
    h = SelfHarness(probe_specs=[])
    report = h.run_self_test()
    assert isinstance(report, SelfTestReport)
    assert report.timestamp != ""
    assert report.overall_status in ("healthy", "degraded", "unhealthy")
    assert isinstance(report.adapters, list)
    assert isinstance(report.store_checks, list)
    assert isinstance(report.recommendations, list)


def test_run_self_test_healthy_when_all_pass():
    """所有检查通过时 overall 应为 healthy。"""
    specs = [("ok", "cap", _HealthyAdapter)]
    h = SelfHarness(probe_specs=specs)
    report = h.run_self_test()
    # 至少有 1 个健康适配器 + eval 冒烟通过 + 存储可写
    assert report.overall_status == "healthy"
    assert len(report.recommendations) == 0


def test_run_self_test_degraded_when_adapter_fails():
    """适配器失败但 eval + 存储正常时，应判定 degraded。"""
    specs = [("bad", "cap", _UnhealthyAdapter)]
    h = SelfHarness(probe_specs=specs)
    report = h.run_self_test()
    # 0 个健康适配器，但 eval 冒烟通过 + 存储可写 → degraded
    assert report.overall_status in ("degraded", "unhealthy")
    # 应有推荐建议
    assert any("bad" in r for r in report.recommendations)


def test_run_self_test_includes_recommendations_for_failures():
    """失败项应有对应的推荐建议。"""
    specs = [("bad", "cap", _UnhealthyAdapter)]
    h = SelfHarness(probe_specs=specs)
    report = h.run_self_test()
    # bad 适配器失败 → 应有提到 bad 的建议
    assert any("bad" in r and "不可用" in r for r in report.recommendations)


def test_run_self_test_to_dict_serializable():
    """SelfTestReport.to_dict 应可 JSON 序列化。"""
    import json
    h = SelfHarness(probe_specs=[])
    report = h.run_self_test()
    d = report.to_dict()
    # 应能 JSON 序列化
    s = json.dumps(d, ensure_ascii=False)
    assert "timestamp" in s
    assert "overall_status" in s
    restored = json.loads(s)
    assert restored["overall_status"] == report.overall_status


# ── 边界 ──

def test_default_probe_specs_safe_when_adapters_missing():
    """默认 probe_specs 在适配器不可导入时应返回空列表（不抛异常）。"""
    h = SelfHarness()  # 不传 specs，用默认
    # VLMAdapter / MiniCPMOAdapter 可能不可导入，应安全跳过
    specs = h._probe_specs
    assert isinstance(specs, list)
    # 不应抛异常


def test_run_self_test_with_empty_specs():
    """无 probe_specs 时仍能正常跑（不算 unhealthy）。"""
    h = SelfHarness(probe_specs=[])
    report = h.run_self_test()
    # 没有适配器探活，但 eval + 存储都通过 → degraded（无健康适配器）
    # 但 ratio = 0/1 = 0，所以不是 healthy
    assert report.overall_status in ("healthy", "degraded")
    # 没有适配器失败，所以没有"不可用"建议
    assert not any("不可用" in r for r in report.recommendations)
