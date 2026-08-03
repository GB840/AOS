"""租户隔离 —— ② 级离线真跑实证（补缺口②）。

验证四层架构第①层「多租户隔离底座」+ 母纲「主权归你，永不收割」在内核
自适应中枢的落地：自适应中枢（稳态 + 失败记忆库）按 tenant_id 维度持有，
A 租户的失败教训绝不串到 B 租户，PREFLIGHT 也不会把 A 的修复注入 B 的规划。

旧版是进程级全局单例 —— 多租户 SaaS 下 A 的失败会被 B 的 PREFLIGHT 读回并
注入其规划，属跨租户数据串味，直接违反母纲。现在：
- tenant_id=None → 共享默认实例（自用模式，行为与旧版零变化）；
- tenant_id 非空 → 该租户独占一套稳态 + 独占失败记忆库文件。

诚实分级：本测试为②级（代码 + 单测实证，不连真 LLM、不连外网）。
③级需真 LLM + 主机环境，本测试不谎报③。

测试纪律：用 set_adaptive_core 把临时路径 core 注入注册表，避免污染项目
_learning_memory/tenants 目录；每个用例前后 reset_adaptive_cores() 隔离状态。
"""

from __future__ import annotations

import json
import os

import pytest

from kernel.adaptive import (
    AdaptiveCore,
    get_adaptive_core,
    set_adaptive_core,
    reset_adaptive_cores,
    list_adaptive_tenants,
    _DEFAULT_TENANT,
)
from kernel.autopilot import _get_autopilot_core, _record_failure_memory


@pytest.fixture(autouse=True)
def _isolate_registry():
    """每个用例前后清空租户注册表，避免跨用例串状态。"""
    reset_adaptive_cores()
    yield
    reset_adaptive_cores()


def _inject(tmp_path, tenant_id):
    """注入一个指向临时文件的租户 core（隔离项目生产库）。"""
    mem = os.path.join(str(tmp_path), f"fm_{tenant_id}.json")
    core = AdaptiveCore(memory_path=mem, tenant_id=tenant_id)
    set_adaptive_core(core, tenant_id)
    return core


def _record(core, task, cap, err):
    core.record_failure(task, cap, err)


# ───────── 隔离①：两租户得到彼此独立的 core 与记忆库 ─────────
def test_two_tenants_get_distinct_cores_and_memory(tmp_path):
    a = _inject(tmp_path, "alpha")
    b = _inject(tmp_path, "beta")

    assert a is not b
    assert a.tenant_id == "alpha"
    assert b.tenant_id == "beta"
    # 记忆库实例互不共享（这是跨租户不串味的物理基础）
    assert a.memory is not b.memory

    # A 写入一次失败，B 不应受影响
    _record(a, "部署订单服务", "web.search", "TimeoutError: 连接超时")
    assert a.memory_stats["total_patterns"] == 1
    assert b.memory_stats["total_patterns"] == 0


# ───────── 隔离②：磁盘文件各自独立（tenant_id 维度落盘） ─────────
def test_tenant_memory_files_are_separate_on_disk(tmp_path):
    a = _inject(tmp_path, "alpha")
    b = _inject(tmp_path, "beta")

    _record(a, "调研竞品", "action.code_exec", "command not found: ffmpeg")

    pa = a.memory._path
    pb = b.memory._path
    # 路径不同
    assert pa != pb
    # A 的磁盘文件确实写进了记录，B 的文件不存在或为空
    assert os.path.exists(pa)
    with open(pa, "r", encoding="utf-8") as f:
        data_a = json.load(f)
    assert len(data_a) == 1
    # B 文件未创建（零记录不落盘）；即便复读也是空
    if os.path.exists(pb):
        with open(pb, "r", encoding="utf-8") as f:
            assert json.load(f) == {}


# ───────── 隔离③：PREFLIGHT 跨租户不泄露教训 ─────────
def test_cross_tenant_preflight_does_not_leak(tmp_path):
    a = _inject(tmp_path, "alpha")
    b = _inject(tmp_path, "beta")

    # A 记录一次「安装 ffmpeg」失败
    _record(a, "安装 ffmpeg", "action.code_exec", "command not found: ffmpeg")

    # 同一任务问 B 的 PREFLIGHT → 必须为空（跨租户不串）
    hints_b = b.fix_hints(task="安装 ffmpeg", capability="action.code_exec")
    assert hints_b == []

    # A 自己能读到自己的教训
    hints_a = a.fix_hints(task="安装 ffmpeg", capability="action.code_exec")
    assert len(hints_a) >= 1

    # 全局 hints（无 task）也互不串：B 全局为空，A 全局含 ffmpeg 修复
    assert b.fix_hints() == []
    assert a.fix_hints() != []
    assert all("ffmpeg" not in h for h in b.fix_hints())


# ───────── 隔离④：注册表 set/reset 生效 ─────────
def test_set_and_reset_adaptive_core_isolation(tmp_path):
    a = _inject(tmp_path, "alpha")
    assert get_adaptive_core(tenant_id="alpha") is a
    assert "alpha" in list_adaptive_tenants()

    # 重置后再次惰性取，应新建一个不同的 core（证明 set 的实例已清除）
    reset_adaptive_cores()
    assert "alpha" not in list_adaptive_tenants()
    a2 = get_adaptive_core(tenant_id="alpha")
    assert a2 is not a
    # 新实例记忆库为空（临时文件独立，未写盘）
    assert a2.memory_stats["total_patterns"] == 0


# ───────── 退化：tenant_id=None 回到共享默认实例（自用模式零变化） ─────────
def test_none_tenant_degrades_to_shared_default(tmp_path):
    d1 = get_adaptive_core(tenant_id=None)
    d2 = get_adaptive_core()                 # 不传 tenant_id
    d3 = get_adaptive_core(tenant_id="")     # 空串等同 None
    assert d1 is d2 is d3                     # 同一个共享默认实例
    assert d1.tenant_id is None
    assert _DEFAULT_TENANT in list_adaptive_tenants()
    # 默认租户记忆库 = FailureMemory 原默认路径（与 LiveEvolutionEngine.adaptive 同文件共享）
    assert d1.memory._path.endswith("failure_memory.json")


# ───────── autopilot 接线：失败记忆按租户隔离写入 + PREFLIGHT 隔离读回 ─────────
def test_autopilot_records_failure_isolated_per_tenant(tmp_path):
    a = _inject(tmp_path, "alpha")
    b = _inject(tmp_path, "beta")

    fake_result = {
        "execution": {
            "trace": [
                {"ok": False, "capability": "web.search",
                 "summary": "连接超时", "error": "TimeoutError: 连接超时"},
            ]
        }
    }

    # 用 autopilot 主路径的失败记忆写入（tenant 维度）
    _record_failure_memory("调研竞品", fake_result, tenant_id="alpha")

    # alpha 写入了 1 条，beta 仍空
    assert a.memory_stats["total_patterns"] == 1
    assert b.memory_stats["total_patterns"] == 0

    # _get_autopilot_core 路由正确：tenant → 对应 core
    assert _get_autopilot_core("alpha") is a
    assert _get_autopilot_core("beta") is b

    # alpha 的 PREFLIGHT 命中，beta 的同任务 PREFLIGHT 不命中（不跨租户串）
    assert _get_autopilot_core("alpha").fix_hints(
        task="调研竞品", capability="web.search") != []
    assert _get_autopilot_core("beta").fix_hints(
        task="调研竞品", capability="web.search") == []


# ───────── 端到端闭环：A 租户写→读改行为 与 B 租户互不干扰 ─────────
def test_tenant_loop_is_closed_within_its_own_namespace(tmp_path):
    a = _inject(tmp_path, "alpha")
    b = _inject(tmp_path, "beta")

    # 两个租户跑「同一个任务」，A 已知失败、B 全新
    _record(a, "安装 ffmpeg", "action.code_exec", "command not found: ffmpeg")

    # A 规划前 PREFLIGHT 注入已知修复；B 不会拿到 A 的修复（隔离）
    preflight_a = _get_autopilot_core("alpha").fix_hints(
        task="安装 ffmpeg", capability="action.code_exec")
    preflight_b = _get_autopilot_core("beta").fix_hints(
        task="安装 ffmpeg", capability="action.code_exec")

    assert preflight_a != []        # A 闭环：写→读
    assert preflight_b == []        # B 不被 A 污染（主权归你）
