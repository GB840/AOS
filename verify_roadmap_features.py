"""路线图 4 项功能端到端验证（P0-b Eval / P1 Replay / P1 HITL / 内容飞轮回写）。

真跑，不弄虚的：每项独立验证，输出 PASS/FAIL 计数。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

tmpdir = tempfile.mkdtemp(prefix="aos_roadmap_")
os.environ["AOS_PULSE_DIR"] = os.path.join(tmpdir, "pulse")
os.environ["AOS_STUDIO_DIR"] = os.path.join(tmpdir, "studio")
os.environ["AOS_HUB_DIR"] = os.path.join(tmpdir, "hub")
os.environ["AOS_EVOLVE_DIR"] = os.path.join(tmpdir, "evolve")
os.environ["AOS_EVAL_DIR"] = os.path.join(tmpdir, "eval")

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"✅ PASS: {name}")
    else:
        failed += 1
        print(f"❌ FAIL: {name}")
    if detail:
        print(f"   {detail}")


# ═══════════════════════════════════════════
# 0. 准备：建工作流 + 跑一次（制造真实运行数据）
# ═════════════════════════════════════════
from kernel.studio.workflow_store import WorkflowStore
from kernel.studio.workflow_runner import WorkflowRunner
from kernel.pulse.pulse_collector import PulseCollector
from kernel.evolve.evolve_engine import EvolveEngine

store = WorkflowStore(base_dir=os.path.join(tmpdir, "studio"))
pulse = PulseCollector()
runner = WorkflowRunner(store=store, pulse=pulse)
evolve = EvolveEngine(pulse=pulse)

wf = store.create("路线图评测工作流", "验证用", author="test")
wf.add_step("web.search", name="搜索")
wf.add_step("inference.llm", name="生成")
store.save(wf)
run = runner.run(wf.id, input_data={"q": "测试"})
check("工作流运行成功", run.status in ("success", "partial"),
      f"status={run.status}, steps={len(run.steps)}")
run_id = run.id
wf_id = wf.id

# ═══════════════════════════════════════════
# 1. P0-b Eval Framework
# ═════════════════════════════════════════
print("\n【1/4】P0-b Eval Framework（任务集提炼 + 轨迹评分 + 回归）")
from kernel.eval.eval_harness import EvalHarness, EvalTask

eh = EvalHarness(store=store, runner=runner)

tasks = eh.build_task_set(min_runs=1, limit=50)
check("从真实运行数据提炼出任务集", len(tasks) >= 1, f"tasks={len(tasks)}")
my_task = next((t for t in tasks if t.workflow_id == wf_id), None)
check("任务集含本工作流", my_task is not None,
      f"task.input={my_task.input_data if my_task else None}")

# 轨迹评分
score = eh.score_trajectory(my_task.id, wf_id, run.steps)
check("轨迹评分生成综合分", 0 <= score.total <= 100, f"total={score.total}")
check("轨迹评分记录步数/失败步", score.step_count == len(run.steps),
      f"step_count={score.step_count}")
check("工具正确性在 0-1", 0.0 <= score.tool_correctness <= 1.0,
      f"tool_correctness={score.tool_correctness}")

# baseline + 回归
baseline = eh.save_baseline(tasks)
check("baseline 建立成功", wf_id in baseline, f"baseline keys={list(baseline.keys())}")
check("baseline 含轨迹分", baseline.get(wf_id, {}).get("total") == score.total)
regs = eh.run_regression(tasks)
check("回归评测可跑", len(regs) >= 1, f"regressions={len(regs)}")
check("首次回归无倒退标记", all(not r.regression for r in regs),
      f"deltas={[r.delta for r in regs]}")

# ═══════════════════════════════════════════
# 2. P1 Replay & Debug
# ═════════════════════════════════════════
print("\n【2/4】P1 Replay & Debug（replay_from_step）")
replay = runner.replay_from_step(run_id, 0)
check("replay 从 step0 重放", replay.get("ok") is True, f"replay={replay.get('ok')}")
check("replay 结果含全部步", replay.get("step_count") == len(run.steps),
      f"step_count={replay.get('step_count')}")
check("replay 标记 replay=True", replay.get("results")
      and all(r.get("replay") for r in replay["results"]),
      "results 应带 replay 标记")
check("replay 不修改原 trace", store.get_run(run_id) is not None
      and store.get_run(run_id).get("status") == run.status)

# what-if：换引擎重放（不应崩）
replay_wf = runner.replay_from_step(run_id, 1, override_engine="ollama")
check("what-if 换引擎重放成功", replay_wf.get("ok") is True,
      f"replay_from={replay_wf.get('replay_from')}")

# ═══════════════════════════════════════════
# 3. P1 HITL 人机协作审批
# ═════════════════════════════════════════
print("\n【3/4】P1 HITL（/api/approvals 后端逻辑）")
from dataclasses import asdict
from kernel.evolve.evolve_engine import OptimizationProposal
import time

# 构造一个中风险提案（target 真实工作流的真实步骤）
prop = OptimizationProposal(
    id="hitl_test_01",
    workflow_id=wf_id,
    proposal_type="step_timeout",
    title="调大生成步骤超时",
    description="生成步骤偶发超时，调大到 60s",
    risk_level="medium",
    expected_benefit="减少超时失败",
    auto_applicable=False,
    change={"action": "update_step", "step_name": "生成", "field": "timeout", "value": 60},
    created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    source="eval",
)
evolve._save_proposal(wf_id, [prop])

pending = evolve.list_pending_approvals(wf_id)
check("中风险提案进入待审队列", any(p.id == "hitl_test_01" for p in pending),
      f"pending={[p.id for p in pending]}")

# 拒绝
rej = evolve.reject_proposal("hitl_test_01", reason="先观察")
check("拒绝提案成功", rej.get("ok") is True)
pending2 = evolve.list_pending_approvals(wf_id)
check("拒绝后不再出现在待审", not any(p.id == "hitl_test_01" for p in pending2))

# 再建一个并确认通过（验证 apply 路径）
prop2 = OptimizationProposal(
    id="hitl_test_02",
    workflow_id=wf_id,
    proposal_type="step_timeout",
    title="调大生成步骤超时(待确认)",
    description="生成步骤偶发超时，调大到 60s",
    risk_level="medium",
    expected_benefit="减少超时失败",
    auto_applicable=False,
    change={"action": "update_step", "step_name": "生成", "field": "timeout", "value": 60},
    created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    source="eval",
)
evolve._save_proposal(wf_id, [prop2])
appr = evolve.approve_proposal("hitl_test_02", store)
check("确认通过并应用提案", appr.get("ok") is True, f"result={appr}")
if appr.get("ok"):
    wf_up = store.get(wf_id)
    gen_step = next((s for s in wf_up.steps if s.name == "生成"), None)
    check("提案已写回工作流(超时=60)", gen_step is not None and gen_step.timeout == 60,
          f"timeout={gen_step.timeout if gen_step else 'N/A'}")

# ═══════════════════════════════════════════
# 4. 内容飞轮自动反哺（反馈 → 策略存储）
# ═════════════════════════════════════════
print("\n【4/4】内容飞轮自动反哺（Echo 反馈 → Evolve → 策略存储）")
from kernel.plugins.content_strategy import ContentStrategyStore

strategy = ContentStrategyStore(path=os.path.join(tmpdir, "evolve", "content_strategy.json"))

# seed 3 条负面内容反馈（触发 content_keyword_adjust 低风险提案）
for i in range(3):
    pulse.record_feedback(f"content_flywheel:AI", {
        "type": "content_feedback",
        "keyword": "AI",
        "total_count": 10,
        "positive_count": 1,
        "negative_count": 9,
        "neutral_count": 0,
        "top_keywords": ["好用", "卡顿", "慢"],
        "needs": ["使用教程"],
    })

applied = evolve.auto_apply_content_proposals("AI", strategy)
check("低风险内容提案被自动应用", len(applied) >= 1,
      f"applied={[a['proposal_type'] for a in applied]}")
if applied:
    st = strategy.get_strategy("AI")
    check("策略存储记录了 boost 关键词", len(st["boost"]) >= 1,
          f"boost={st['boost']}")
    check("策略存储记录了 reduce 话题", len(st["reduce"]) >= 1,
          f"reduce={st['reduce']}")

# ═══════════════════════════════════════════
print("\n" + "=" * 70)
print(f"路线图功能验证：{passed} passed, {failed} failed")
print("=" * 70)

if failed > 0:
    print("\n❌ 有失败项")
    sys.exit(1)
else:
    print("\n✅ 全部通过！4 项功能（Eval / Replay / HITL / 内容回写）端到端验证成功")
    sys.exit(0)
