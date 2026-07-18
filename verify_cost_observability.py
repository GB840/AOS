"""Task 1: Cost Observability 端到端验证。

真跑验证，不弄虚的：
1. token 计数（tiktoken + 字符回退）
2. 成本估算（按模型定价表）
3. Pulse 接收 token_usage 字段、自动转记到 CostTracker
4. CostTracker 落盘 + 聚合查询（按 model/workflow/user/agent 维度）
5. 成本告警：阈值触发 + 自动检查
6. Evolve 基于成本数据生成 cost_optimization / model_switch 提案
7. WorkflowRunner 从 step_result 提取 token_usage（usage 字段 + 文本估算两种路径）

全链路：步骤 token 用量 → CostTracker → Pulse metrics → Evolve 提案 → 写回工作流
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

tmpdir = tempfile.mkdtemp(prefix="aos_cost_")
os.environ["AOS_PULSE_DIR"] = os.path.join(tmpdir, "pulse")
os.environ["AOS_STUDIO_DIR"] = os.path.join(tmpdir, "studio")
os.environ["AOS_HUB_DIR"] = os.path.join(tmpdir, "hub")
os.environ["AOS_EVOLVE_DIR"] = os.path.join(tmpdir, "evolve")

print(f"测试临时目录: {tmpdir}")
print("=" * 70)

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"✅ PASS: {name}")
    else:
        failed += 1
        print(f"❌ FAIL: {name}")
    if detail:
        print(f"   {detail}")


# ── 1. Token 计数 ──
print("\n【1/7】Token 计数：tiktoken + 字符回退")

from kernel.pulse.cost_tracker import count_tokens, estimate_cost, CostTracker, reset_cost_tracker_for_test

# 重置单例（保证干净环境）
reset_cost_tracker_for_test()

# 英文 token
en_text = "Hello world, this is a test of the token counting system."
en_tokens = count_tokens(en_text)
check("英文 token 计数 > 0", en_tokens > 0, f"tokens={en_tokens}, text='{en_text[:40]}...'")

# 中文 token
zh_text = "你好世界，这是一个 token 计数系统的测试。"
zh_tokens = count_tokens(zh_text)
check("中文 token 计数 > 0", zh_tokens > 0, f"tokens={zh_tokens}, text='{zh_text}'")

# 空文本
check("空文本返回 0", count_tokens("") == 0)

# tiktoken 应可用
import tiktoken
enc = tiktoken.get_encoding("cl100k_base")
expected = len(enc.encode(en_text))
check("tiktoken 直接对照", en_tokens == expected,
      f"count_tokens={en_tokens}, tiktoken={expected}")


# ── 2. 成本估算 ──
print("\n【2/7】成本估算：按模型定价表")

# GPT-4o: prompt $0.005/1K, completion $0.015/1K
cost_gpt4o = estimate_cost(prompt_tokens=1000, completion_tokens=500, model="gpt-4o")
expected_gpt4o = 1000 / 1000 * 0.005 + 500 / 1000 * 0.015
check("GPT-4o 成本计算正确", abs(cost_gpt4o - expected_gpt4o) < 0.000001,
      f"actual={cost_gpt4o}, expected={expected_gpt4o:.6f}")

# 本地模型零成本
cost_local = estimate_cost(prompt_tokens=10000, completion_tokens=10000, model="qwen2.5:7b")
check("本地模型零成本", cost_local == 0.0, f"cost=${cost_local}")

# 未知模型走默认定价
cost_default = estimate_cost(prompt_tokens=1000, completion_tokens=0, model="some-unknown-model-xyz")
expected_default = 1000 / 1000 * 0.002
check("未知模型走默认定价", abs(cost_default - expected_default) < 0.000001,
      f"actual={cost_default}, expected={expected_default:.6f}")

# 前缀匹配（gpt-4o-2024-08-06 匹配 gpt-4o）
cost_prefix = estimate_cost(prompt_tokens=1000, completion_tokens=500, model="gpt-4o-2024-08-06")
check("模型前缀匹配", cost_prefix == cost_gpt4o,
      f"gpt-4o-2024-08-06=${cost_prefix}, gpt-4o=${cost_gpt4o}")


# ── 3. PulseCollector 接收 token_usage ──
print("\n【3/7】PulseCollector 接收 token_usage 字段，自动转记到 CostTracker")

from kernel.pulse.pulse_collector import PulseCollector
pulse = PulseCollector()

# 模拟 6 次运行，含 token_usage
for i in range(6):
    pulse.record_run("wf_test_cost", {
        "status": "success",
        "duration": 5.0 + i,
        "run_id": f"run_{i}",
        "token_usage": {
            "model": "gpt-4o",
            "prompt_tokens": 1000 + i * 100,
            "completion_tokens": 500 + i * 50,
            "user_id": "user_alice",
            "agent_id": "litellm",
            "run_id": f"run_{i}",
        },
    })

# 查 metrics 是否累计了 token
metrics = pulse.get_agent_metrics("wf_test_cost")
check("Pulse metrics 含 total_tokens",
      metrics.get("total_tokens", 0) > 0,
      f"total_tokens={metrics.get('total_tokens', 0)}")
check("Pulse metrics 含 total_cost_usd",
      metrics.get("total_cost_usd", 0) > 0,
      f"total_cost_usd=${metrics.get('total_cost_usd', 0)}")

# 期望总 prompt_tokens = 1000+1100+1200+1300+1400+1500 = 7500
# 期望总 completion_tokens = 500+550+600+650+700+750 = 3750
expected_total_tokens = 7500 + 3750
check("Token 累计正确", metrics.get("total_tokens", 0) == expected_total_tokens,
      f"actual={metrics.get('total_tokens', 0)}, expected={expected_total_tokens}")


# ── 4. CostTracker 聚合查询 ──
print("\n【4/7】CostTracker 多维度聚合查询")

# 按 workflow 聚合
bd = pulse.get_cost_breakdown(workflow_id="wf_test_cost")
check("CostTracker 聚合 ok", bd.get("ok") is True)
check("CostTracker 总成本 > 0", bd.get("total_cost", 0) > 0,
      f"total_cost=${bd.get('total_cost', 0):.6f}")
check("CostTracker 总 token 数正确",
      bd.get("total_tokens") == expected_total_tokens,
      f"actual={bd.get('total_tokens')}, expected={expected_total_tokens}")

# 按 model 维度
check("by_model 含 gpt-4o",
      "gpt-4o" in bd.get("by_model", {}),
      f"by_model={bd.get('by_model')}")

# 按 user 维度
check("by_user 含 user_alice",
      "user_alice" in bd.get("by_user", {}),
      f"by_user={bd.get('by_user')}")

# 按 agent 维度
check("by_agent 含 litellm",
      "litellm" in bd.get("by_agent", {}),
      f"by_agent={bd.get('by_agent')}")

# 按 user_id 过滤
bd_alice = pulse.get_cost_breakdown(user_id="user_alice")
check("按 user 过滤生效",
      bd_alice.get("total_tokens") == expected_total_tokens,
      f"alice 总 token={bd_alice.get('total_tokens')}")

# 查最近记录
records = pulse.get_cost_records(limit=10, workflow_id="wf_test_cost")
check("get_cost_records 返回非空",
      len(records) > 0,
      f"records count={len(records)}")
check("记录按时间倒序",
      all(records[i].get("timestamp", "") >= records[i + 1].get("timestamp", "")
          for i in range(len(records) - 1)),
      "timestamp 应倒序")


# ── 5. 成本告警 ──
print("\n【5/7】成本告警：阈值触发")

# 创建一个 daily 阈值 $0.001 的告警（极低阈值，必然触发）
result = pulse.add_cost_alert(
    name="alice 成本超 $0.001/日",
    scope="user",
    scope_id="user_alice",
    period="daily",
    threshold_usd=0.001,
)
check("告警创建成功", result.get("ok") is True, f"alert_id={result.get('alert_id')}")

# 列出告警
alerts = pulse.list_cost_alerts()
check("告警列表非空", len(alerts) >= 1, f"alerts count={len(alerts)}")

# 主动检查
triggered = pulse.check_cost_alerts()
check("告警触发", len(triggered) >= 1,
      f"triggered count={len(triggered)}")
if triggered:
    t = triggered[0]
    check("告警内容正确",
          t.get("scope") == "user" and t.get("scope_id") == "user_alice",
          f"triggered={t}")
    check("告警实际成本 > 阈值",
          t.get("actual_cost", 0) > t.get("threshold_usd", 0),
          f"actual=${t.get('actual_cost', 0):.6f}, threshold=${t.get('threshold_usd', 0):.6f}")

# 删除告警
alert_id = result["alert_id"]
deleted = pulse.delete_cost_alert(alert_id)
check("告警删除成功", deleted is True)
check("告警删除后列表减少",
      len(pulse.list_cost_alerts()) == len(alerts) - 1)


# ── 6. Evolve 成本提案 ──
print("\n【6/7】Evolve 基于成本数据生成提案")

from kernel.evolve.evolve_engine import EvolveEngine
evolve = EvolveEngine(pulse=pulse)

# wf_test_cost 的 avg_tokens_per_run = 11250/6 = 1875，低于 4000 阈值，
# 不应触发 cost_optimization 提案（合理：token 量本就不高）
proposals = evolve.generate_proposals("wf_test_cost")
check("wf_test_cost 不触发成本提案（avg < 4000）",
      len(proposals) == 0,
      f"proposals count={len(proposals)}（应为 0）")

# 创建一个真正高 token 的工作流来验证成本提案
from kernel.studio.workflow_models import Workflow
from kernel.studio.workflow_store import WorkflowStore
store = WorkflowStore(base_dir=os.path.join(tmpdir, "studio"))
wf = Workflow.create("成本测试工作流", "验证成本提案写回", author="test")
wf.add_step(capability="inference.llm", name="LLM 步骤", prompt="分析数据")
wf.add_step(capability="web.search", name="搜索步骤", prompt="搜索数据")
store.save(wf)

# 给这个工作流注入高 token 数据（avg > 4000）
# 3000 prompt + 2000 completion = 5000 tokens/run，6 次共 30000 tokens
for i in range(6):
    pulse.record_run(wf.id, {
        "status": "success",
        "duration": 5.0,
        "run_id": f"wf2_run_{i}",
        "token_usage": {
            "model": "gpt-4o",
            "prompt_tokens": 3000,
            "completion_tokens": 2000,
            "user_id": "user_bob",
            "agent_id": "litellm",
        },
    })

proposals2 = evolve.generate_proposals(wf.id, workflow_store=store)
cost_props2 = [p for p in proposals2 if p.proposal_type == "cost_optimization"]
check("wf2 生成 cost_optimization 提案（avg=5000 > 4000）",
      len(cost_props2) > 0,
      f"cost_optimization 提案数={len(cost_props2)}")

if cost_props2:
    cp2 = cost_props2[0]
    check("cost_optimization 是低风险", cp2.risk_level == "low",
          f"risk_level={cp2.risk_level}")
    check("cost_optimization 可自动应用", cp2.auto_applicable is True,
          f"auto_applicable={cp2.auto_applicable}")
    check("cost_optimization change.action=update_step",
          cp2.change.get("action") == "update_step",
          f"change={cp2.change}")
    check("cost_optimization 设置 max_tokens=2048",
          cp2.change.get("field") == "max_tokens" and cp2.change.get("value") == 2048,
          f"change={cp2.change}")
    check("change.step_name 是真实步骤名（非 pattern）",
          cp2.change.get("step_name") == "LLM 步骤",
          f"step_name='{cp2.change.get('step_name')}'")

    # 应用成本优化提案
    result = evolve.apply_proposal(cp2.id, store)
    check("成本提案应用成功", result.get("ok") is True,
          f"result={result}")
    if result.get("ok"):
        # 验证步骤被修改了
        wf_updated = store.get(wf.id)
        llm_step = next((s for s in wf_updated.steps
                         if s.capability == "inference.llm"), None)
        check("LLM 步骤 max_tokens 已设为 2048",
              llm_step is not None and llm_step.max_tokens == 2048,
              f"max_tokens={llm_step.max_tokens if llm_step else 'N/A'}")
        check("工作流版本号递增",
              wf_updated.version != "1.0.0",
              f"version={wf_updated.version}")

        # 验证 to_chiplet_step 把 max_tokens 传到 payload
        chiplet_step = llm_step.to_chiplet_step()
        check("to_chiplet_step 传 max_tokens 到 payload",
              chiplet_step.get("payload", {}).get("max_tokens") == 2048,
              f"payload={chiplet_step.get('payload')}")


# ── 7. WorkflowRunner 从 step_result 提取 token usage ──
print("\n【7/7】WorkflowRunner 从步骤结果提取 token usage")

from kernel.studio.workflow_runner import WorkflowRunner

runner = WorkflowRunner(pulse=pulse, store=store)

# 模拟 1：引擎返回 usage 字段（OpenAI 标准）
step_with_usage = {
    "step_name": "LLM 调用",
    "capability": "inference.llm",
    "engine": "litellm",
    "ok": True,
    "duration": 2.5,
    "output": {
        "content": "这是 LLM 生成的回答",
        "model": "gpt-4o",
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 80,
            "total_tokens": 230,
        },
    },
    "run_id": "test_run_1",
    "workflow_id": wf.id,
}

tu1 = runner._extract_token_usage(step_with_usage)
check("从 usage 字段提取 token 用量", tu1 is not None,
      f"tu={tu1}")
if tu1:
    check("usage 提取 prompt_tokens 正确", tu1["prompt_tokens"] == 150,
          f"actual={tu1['prompt_tokens']}")
    check("usage 提取 completion_tokens 正确", tu1["completion_tokens"] == 80,
          f"actual={tu1['completion_tokens']}")
    check("usage 提取 model 正确", tu1["model"] == "gpt-4o",
          f"actual={tu1['model']}")

# 模拟 2：引擎没返回 usage，但有 content 文本（走文本估算路径）
step_text_only = {
    "step_name": "Ollama 调用",
    "capability": "inference.llm",
    "engine": "ollama",
    "ok": True,
    "duration": 1.8,
    "output": {
        "content": "这是 Ollama 本地模型生成的较长回答，用于测试文本估算路径。" * 5,
        "model": "qwen2.5:7b",
    },
    "run_id": "test_run_2",
    "workflow_id": wf.id,
}

tu2 = runner._extract_token_usage(step_text_only)
check("从文本估算 token 用量", tu2 is not None,
      f"tu={tu2}")
if tu2:
    check("文本估算 completion_tokens > 0", tu2["completion_tokens"] > 0,
          f"completion_tokens={tu2['completion_tokens']}")
    check("文本估算 prompt_tokens=0（无法恢复）", tu2["prompt_tokens"] == 0,
          f"prompt_tokens={tu2['prompt_tokens']}")

# 模拟 3：非 LLM 步骤（不该提取 token）
step_search = {
    "step_name": "搜索步骤",
    "capability": "web.search",
    "engine": "duckduckgo",
    "ok": True,
    "output": {"results": ["url1", "url2"]},
}
tu3 = runner._extract_token_usage(step_search)
check("非 LLM 步骤不提取 token", tu3 is None,
      f"tu={tu3}")

# 触发 _report_step 真正写入 CostTracker（用 step_with_usage）
runner._report_step(wf.id, step_with_usage)

# 验证 CostTracker 多了一条记录
records_after = pulse.get_cost_records(limit=100, workflow_id=wf.id)
# 注意：wf.id 之前在 record_run 时已经写过 6 条，这里又加了 1 条 step 级记录
check("步骤上报后 CostTracker 记录数增加",
      len(records_after) >= 7,
      f"records count={len(records_after)}")

# 验证新增的记录是 step 级的（run_id=test_run_1）
step_record = next((r for r in records_after if r.get("run_id") == "test_run_1"), None)
check("新增记录是 step 级的（run_id=test_run_1）",
      step_record is not None,
      f"records={[r.get('run_id') for r in records_after]}")
if step_record:
    check("step 级记录 prompt_tokens=150",
          step_record.get("prompt_tokens") == 150,
          f"actual={step_record.get('prompt_tokens')}")
    check("step 级记录 agent_id=litellm",
          step_record.get("agent_id") == "litellm",
          f"actual={step_record.get('agent_id')}")


# ── 总结 ──
print("\n" + "=" * 70)
print(f"测试结果：{passed} passed, {failed} failed")
print("=" * 70)

if failed > 0:
    print("\n❌ 有失败项，需排查")
    sys.exit(1)
else:
    print("\n✅ 全部通过！Task 1: Cost Observability 端到端验证成功")
    print("\n落地清单：")
    print("  - src/kernel/pulse/cost_tracker.py（新）—— Token 计数 + 成本估算 + CostTracker + CostAlert")
    print("  - src/kernel/pulse/pulse_collector.py（扩展）—— record_run 支持 token_usage 字段、新增 cost 查询方法")
    print("  - src/kernel/studio/workflow_runner.py（扩展）—— _report_step 提取 token usage、_aggregate_run_tokens 汇总")
    print("  - src/kernel/evolve/evolve_engine.py（扩展）—— _generate_cost_proposals 生成 3 类成本提案")
    print("  - src/api/product_flywheel_api.py（扩展）—— 6 个 /api/pulse/costs* 端点")
    sys.exit(0)
