# AOS 路线图 5 项能力落地验证报告

> 生成时间：2026-07-18 | commit：`873e515`（feature/infra-setup）
> 原则：可验证即真理 —— 所有结论均来自真实跑通的验证脚本，非口头声明。

## 一、总览

| # | 能力 | 状态 | 验证脚本 | 结果 |
|---|------|------|----------|------|
| 1 | P0-b Eval Framework | ✅ 落地 | `verify_roadmap_features.py` | 9/9 PASS |
| 2 | P1 Cost Observability | ✅ 落地（前序完成，本次复核） | `verify_cost_observability.py` | 50/50 PASS |
| 3 | P1 HITL 审批闭环 | ✅ 落地 | `verify_roadmap_features.py` | 5/5 PASS |
| 4 | P1 Replay & Debug | ✅ 落地 | `verify_roadmap_features.py` | 5/5 PASS |
| 5 | 内容飞轮自动反哺 | ✅ 落地 | `verify_roadmap_features.py` | 4/4 PASS |

**合计：路线图脚本 23/23 PASS + 成本脚本 50/50 PASS = 73 项断言全绿。**

## 二、P0-b Eval Framework（新文件 `src/kernel/eval/eval_harness.py`）

长在已有基建上（WorkflowStore 任务来源 + WorkflowRunner 执行 + Pulse 数据），不重造。

- `EvalTask`：源自真实工作流的评测任务（输入 + 期望能力路径）
- `TrajectoryScore`：step 级评分 —— 工具正确性 0.4 + 路径连贯 0.3 + 步数最优 0.3，综合 0-100
- `EvalHarness.build_task_set`：从真实运行历史提炼任务集（需有 runs 才纳入）
- `EvalHarness.run_regression`：工作流变更后重跑对比 baseline，标记倒退

真跑证据：
```
✅ PASS: 从真实运行数据提炼出任务集           tasks=1
✅ PASS: 任务集含本工作流                     task.input={'q': '测试'}
✅ PASS: 轨迹评分生成综合分                   total=65.0
✅ PASS: baseline 建立成功                    baseline keys=['ee4a8a717881']
✅ PASS: 首次回归无倒退标记                   deltas=[0.0]
```

## 三、P1 Cost Observability（前序完成，本次复核）

- `src/kernel/pulse/cost_tracker.py`：tiktoken 计数 + 定价表 + CostTracker + CostAlert
- `product_flywheel_api.py`：6 个 `/api/pulse/costs*` 端点
- Evolve 三类 cost 提案（cost_optimization / model_switch / cost_alert）

真跑证据（`verify_cost_observability.py`）：
```
✅ PASS: 从 usage 字段提取 token 用量         tu={'model': 'gpt-4o', 'prompt_tokens': 150, ...}
✅ PASS: 步骤上报后 CostTracker 记录数增加     records count=7
✅ PASS: step 级记录 prompt_tokens=150
==================================================================
测试结果：50 passed, 0 failed
```

## 四、P1 HITL（改 `evolve_engine.py` + `product_flywheel_api.py`）

- `OptimizationProposal` 新增 4 字段：`approved / approved_at / rejected / reject_reason`
- `list_pending_approvals`：仅中/高风险、未应用、未拒绝的提案进待审队列
- `approve_proposal`：人工确认 → 调用 `apply_proposal` 真写回工作流 + 回滚快照
- `reject_proposal`：标记拒绝、不应用（便于审计）
- `GET/POST /api/approvals/{id}/approve|reject` + `GET /api/approvals/panel`（HTML 审批面板）

真跑证据（含写回实证）：
```
✅ PASS: 中风险提案进入待审队列               pending=['hitl_test_01']
✅ PASS: 拒绝提案成功
✅ PASS: 拒绝后不再出现在待审
✅ PASS: 确认通过并应用提案
   result={'ok': True, 'step': '生成', 'field': 'timeout',
           'old_value': 120, 'new_value': 60, 'rollback_available': True}
✅ PASS: 提案已写回工作流(超时=60)           timeout=60
```

## 五、P1 Replay & Debug（改 `workflow_runner.py` + `workflow_store.py`）

- `replay_from_step(trace_id, step_index, override_engine=, override_payload=)`：
  从指定步骤断点重放，支持 what-if 换引擎 / 注入 payload
- 纯调试原语：只读原 trace + 工作流定义，**不写 Pulse、不触发 Evolve、不污染原 trace**
- `workflow_store.get_run(run_id)`：按 run_id 取记录供回放

真跑证据：
```
✅ PASS: replay 从 step0 重放                replay=True
✅ PASS: replay 结果含全部步                 step_count=2
✅ PASS: replay 标记 replay=True
✅ PASS: replay 不修改原 trace
✅ PASS: what-if 换引擎重放成功              replay_from=1
```

## 六、内容飞轮自动反哺（新 `content_strategy.py` + 改 `content_flywheel.py`/`evolve_engine.py`）

双飞轮内容侧闭环打通：Echo 负面反馈 → Pulse → Evolve 生成提案 → 自动写回策略存储。

- `generate_content_proposals`：读内容反馈，产出 `content_keyword_adjust`（低风险）/ `content_topic_suggestion`（中风险）
- `auto_apply_content_proposals`：低风险自动写回 `ContentStrategyStore`（boost/reduce/topics JSON 落盘）；中高风险不自动应用、进审批队列
- `ContentStrategyStore`：内容生成阶段可读取的偏好策略载体

真跑证据：
```
✅ PASS: 低风险内容提案被自动应用            applied=['content_keyword_adjust']
✅ PASS: 策略存储记录了 boost 关键词         boost=['好用', '卡顿']
✅ PASS: 策略存储记录了 reduce 话题          reduce=['负面相关话题']
```

## 七、提交记录

```
873e515 feat: 落地路线图5项能力(Eval/成本可观测/HITL/回放/内容飞轮反哺)
 16 files changed, 4095 insertions(+), 44 deletions(-)
```

提交范围（仅功能相关 + 直接支撑的双飞轮/Evolve 基础，未带入 debug 草稿）：
- 新增：`src/kernel/eval/eval_harness.py`、`src/kernel/plugins/content_strategy.py`、`src/kernel/pulse/cost_tracker.py`、`verify_roadmap_features.py`、`verify_cost_observability.py`
- 修改：`evolve_engine.py`、`product_flywheel_api.py`、`workflow_runner.py`、`workflow_store.py`、`content_flywheel.py`、`pulse_collector.py`、`main.py`、`echo_adapter.py`、`workflow_models.py`、`hub_store.py`、`autoskill_engine.py`

本地领先 origin 1 个提交。待你在主机执行推送：
```
git push origin feature/infra-setup
```
