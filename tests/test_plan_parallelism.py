"""依赖感知并行规划测试。

覆盖用户诉求「不能多线程干活 / 不会规划好再去」的落地：
  - plan_bridge.plan_with_parallelism —— 本地启发式：识别独立同能力 fan-out 产 parallel_groups；
  - plan_bridge.parse_plan_with_parallelism —— ag2 路径：解析 `PARALLEL:` 声明；
  - autopilot._plan / _cap_parallel_groups —— 开关门控 + 首轮透传 + 并发上限裁剪。

核心不变量（引擎约束，违反即回归）：
  1. 并行步必须自带独立 in:{task}（不用 in_from:previous，杜绝并发竞态）；
  2. parallel_groups 必须覆盖【从0起连续前缀】；拿不准一律 None（完全串行、零回归）。
"""
from __future__ import annotations

from kernel.plugins.plan_bridge import (
    plan_with_parallelism,
    parse_plan_with_parallelism,
)

# 测试用能力集（含并行安全 + 副作用能力，用于验证白名单过滤）
_CAPS = [
    "web.search", "web.fetch", "action.code_exec", "inference.llm",
    "memory.semantic", "cognition.reasoning", "media.image",
]


# —————————————————— heuristic 路径：plan_with_parallelism ——————————————————

def test_fanout_same_cap_list_grouped():
    """列举式同能力 fan-out → 一个并行组，每步独立 in:{task}（能力继承）。"""
    steps, groups = plan_with_parallelism("分别搜索A、B、C", _CAPS)
    assert groups == [[0, 1, 2]]
    assert len(steps) == 3
    for st in steps:
        assert st["capability"] == "web.search"
        assert "in" in st and "in_from" not in st  # 独立输入，无并发竞态
        assert st["in"]["task"]  # 非空


def test_parallel_connective_grouped():
    """并列连词「并」连接的同能力步 → 并发。"""
    steps, groups = plan_with_parallelism("搜索A并搜索B", _CAPS)
    assert groups == [[0, 1]]
    assert all(s["capability"] == "web.search" and "in" in s for s in steps[:2])


def test_sequential_connective_stays_serial():
    """顺序连词「然后」= 先后依赖 → 完全退回串行（parallel_groups=None）。"""
    steps, groups = plan_with_parallelism("搜索A 然后 总结结果", _CAPS)
    assert groups is None
    # 退回既有 heuristic_plan 语义：首步 in、后续 in_from:previous
    assert "in" in steps[0]


def test_different_caps_not_parallelized():
    """不同能力（写代码 vs 执行）不并行 → None。"""
    steps, groups = plan_with_parallelism("写代码并执行", _CAPS)
    assert groups is None


def test_side_effect_cap_never_parallelized():
    """副作用能力（代码执行）即便是同能力 fan-out 也绝不并行（白名单外）。"""
    steps, groups = plan_with_parallelism("运行脚本A、运行脚本B", _CAPS)
    assert groups is None


def test_single_step_stays_serial():
    """拆不出 ≥2 段 → None。"""
    _steps, groups = plan_with_parallelism("搜索一个东西", _CAPS)
    assert groups is None


def test_fanout_then_sequential_remainder():
    """fan-out 前缀并行 + 顺序余部：组覆盖前缀、余部串行衔接。"""
    steps, groups = plan_with_parallelism("搜索A、搜索B，然后总结", _CAPS)
    assert groups == [[0, 1]]
    # 前两步独立并行输入
    assert "in" in steps[0] and "in" in steps[1]
    # 余部（总结/桥接）用 in_from:previous 串接
    assert any(s.get("in_from") == "previous" for s in steps[2:])


def test_parallel_group_is_leading_prefix():
    """并行组必须是从0起的连续前缀（引擎约束）。"""
    _steps, groups = plan_with_parallelism("分别搜索X、Y、Z", _CAPS)
    covered = sorted({i for g in groups for i in g})
    assert covered == list(range(len(covered)))
    assert covered[0] == 0


# —————————————————— ag2 路径：parse_plan_with_parallelism ——————————————————

def test_ag2_parallel_line_parsed():
    """ag2 计划带 `PARALLEL: 1,2` → 解析成 [[0,1]]，被覆盖步转独立 in:{task}。"""
    plan = (
        "1. [web.search] latest AI chips news\n"
        "2. [web.search] latest GPU market news\n"
        "3. [inference.llm] summarize both findings\n"
        "PARALLEL: 1,2\n"
    )
    steps, groups = parse_plan_with_parallelism(plan, _CAPS)
    assert groups == [[0, 1]]
    assert len(steps) == 3
    # 并行步无 in_from（独立输入），第3步保持顺序
    assert "in_from" not in steps[0] and "in_from" not in steps[1]
    assert steps[0]["in"]["task"] and steps[1]["in"]["task"]
    assert steps[2].get("in_from") == "previous"


def test_ag2_non_leading_parallel_rejected():
    """PARALLEL 非「从0起连续前缀」→ 保守丢弃，退回串行。"""
    plan = (
        "1. [inference.llm] think first\n"
        "2. [web.search] search A\n"
        "3. [web.search] search B\n"
        "PARALLEL: 2,3\n"
    )
    steps, groups = parse_plan_with_parallelism(plan, _CAPS)
    assert groups is None
    assert len(steps) == 3


def test_ag2_no_parallel_line_serial():
    """无 PARALLEL 行 → None（零回归，与 parse_plan_to_steps 一致）。"""
    plan = (
        "1. [web.search] search something\n"
        "2. [inference.llm] summarize\n"
    )
    steps, groups = parse_plan_with_parallelism(plan, _CAPS)
    assert groups is None
    assert len(steps) == 2


def test_ag2_single_step_parallel_ignored():
    """PARALLEL 只列 1 个步号（<2）→ 忽略（无意义），退回串行。"""
    plan = (
        "1. [web.search] search\n"
        "2. [inference.llm] summarize\n"
        "PARALLEL: 1\n"
    )
    _steps, groups = parse_plan_with_parallelism(plan, _CAPS)
    assert groups is None


# —————————————————— autopilot 集成：开关门控 + 上限裁剪 ——————————————————

def test_autopilot_cap_parallel_groups():
    """并发上限裁剪：超上限的组切成 ≤max 的连续子组，覆盖范围不变。"""
    from kernel.autopilot import _cap_parallel_groups
    assert _cap_parallel_groups([[0, 1, 2, 3, 4]], 3) == [[0, 1, 2], [3, 4]]
    assert _cap_parallel_groups([[0, 1]], 3) == [[0, 1]]
    assert _cap_parallel_groups(None, 3) is None


def test_autopilot_parallel_flag_default_off(monkeypatch):
    """默认关：不设 env → _plan 不产 parallel_groups（零回归）。"""
    import kernel.autopilot as ap
    monkeypatch.delenv("AOS_AUTOPILOT_PARALLEL", raising=False)
    assert ap._parallel_enabled() is False
    _pt, steps, groups, planner = ap._plan("分别搜索A、B、C", "heuristic")
    assert groups is None
    assert steps  # 仍能串行规划


def test_autopilot_parallel_flag_on_activates(monkeypatch):
    """开关开启 + heuristic 规划 → _plan 产出 parallel_groups 并首轮可透传。"""
    import kernel.autopilot as ap
    monkeypatch.setenv("AOS_AUTOPILOT_PARALLEL", "1")
    monkeypatch.setenv("AOS_MAX_PARALLEL", "3")
    _pt, steps, groups, planner = ap._plan("分别搜索A、B、C", "heuristic")
    assert groups == [[0, 1, 2]]
    assert planner == "heuristic"
    for i in groups[0]:
        assert "in" in steps[i] and "in_from" not in steps[i]


def test_finalize_verb_breaks_parallel_run():
    """收尾动词（汇总/总结）强制顺序：并行游程在它之前断掉，且汇总步是
    inference.llm（非 web.search）、顺序衔接——『搜索A、B、C 并汇总』应是
    [0,1,2] 并发 + 汇总顺序，而非把汇总错并进并行组。"""
    steps, groups = plan_with_parallelism("分别搜索A、B、C 并汇总", _CAPS)
    assert groups == [[0, 1, 2]]
    # 并行组内均为 web.search 且独立输入（无并发竞态）
    for i in groups[0]:
        assert steps[i]["capability"] == "web.search"
        assert "in" in steps[i]
    # 余部（汇总/桥接）必为 inference.llm 且顺序衔接，绝不 web.search
    tail = steps[3:]
    assert tail
    assert all(s["capability"] == "inference.llm" and s.get("in_from") == "previous"
               for s in tail)
    assert not any(s["capability"] == "web.search" for s in tail)


def test_quantifier_phrase_stripped_from_search_term():
    """列举量词尾巴（『三个主题』）从末项搜索词剥掉，查询干净。"""
    steps, _g = plan_with_parallelism(
        "分别搜索 人工智能、量子计算、区块链 三个主题并汇总", _CAPS)
    search_steps = [s for s in steps if s["capability"] == "web.search"]
    assert len(search_steps) == 3
    assert all("三个主题" not in s["in"]["task"] for s in search_steps)
