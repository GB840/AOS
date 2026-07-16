# AOS 全盘核查报告（2026-07-17）

> 触发：用户 push `a28f030` 后要求"从新全盘检查"，在我动手加"路由预测器"之前先摸清现状，避免破坏现有功能、混淆责任边界。
> 方法：git 状态 + 核心模块 import 实测 + pytest 真实跑（系统 Python 3.14.5 / pytest 9.1.1）+ `FabricHub.health_report()` 实测引擎注册数。所有结论附可复核证据。

---

## 1. 版本控制状态

- **HEAD**：`a28f030` feat: P1 多Agent代码团队 + 质量门三分规则（已 push 到 `feature/infra-setup`，`a7ef9b2..a28f030`）。
- **未提交改动（14 文件，+126/−48）**：经逐文件 diff 核对，**全部良性维护，无破坏性**，且**未触碰 `registry.py` 的路由逻辑**：
  - `src/core/fabric/registry.py`：仅删除一个未使用的 `ENGINE_TIER` import（无害清理）。
  - `src/core/fabric/adapters/vlm_adapter.py`：仅删除未使用的 `Any` import。
  - `src/kernel/plugins/fabric_hub.py`：会话历史加 LRU 上限（最多保留最近 5 轮）。
  - `src/kernel/autopilot.py`（+81 行）：反思记忆加 TTL 生命周期（短期故障 7 天 / 长期偏好 90 天）+ trace 增加 `memory_recall` 字段；**不涉及路由/registry**。
  - `tests/test_fabric_hub.py`：新增 2 个会话 LRU 测试。
  - `tools/baseline_snapshot.py`：修复工具自身 import（加 `sys.path` + import fabric_hub）。
  - `AGENTS.md`：基线表更新（测试数 428→480 collected）；但"适配器总数"仍写 20（**已过时，见 §3**）。
  - 其余 adapter 小改（清无用 import）。
- **未跟踪（4 项）**：
  - `tests/test_autopilot.py`、`tests/test_semantic_state.py` → **合法新测试，应进库**。
  - `.arts/`（编辑器 `settings.json`）、`coverage.json`（覆盖率产物）→ **应加 `.gitignore`**，否则 `git add .` 会污染版本库（见 §6）。

> 注：这批未提交改动的来源不在本会话内（可能来自后台覆盖率任务/其他会话），建议先确认意图再提交。

---

## 2. 测试健康（真实跑，非估计）

| 范围 | 结果 |
|------|------|
| 我上轮落地模块（vlm / a2ui / code_team / compliance_gate / memory_compression / tier_routing / route_failover） | **48 passed** ✅ |
| 未跟踪新测试（test_autopilot / test_semantic_state） | **2 passed** ✅ |
| `test_fabric_hub.py` | **2 failed / 5 passed** ❌ |

**总计：50 绿 / 2 红。**

### 2.1 红测试根因（精确）
文件 `tests/test_fabric_hub.py`，失败两例：
- `test_registers_all_six_and_reports_total`
- `test_kernel_delegates_resolve_engine_to_hub`

断言：`rep["total"] == len(_EXPECTED_ENGINES)`，期望 **20**，实际 `health_report()["total"] ==` **24**。
`health_report()` 实测返回的 24 个引擎全部合法，`_EXPECTED_ENGINES` 集合里一个都没少（`IN_EXPECTED_BUT_ABSENT` 为空）——**纯属测试常量落后于实现，无重复注册、无 bug**。

实际 24 个（已排序）：
```
ag2, agnes, browser-use, code-exec, codebase-memory-mcp, desktop-touch, file-io,
langfuse, lfm2, litellm, lnn, mem0, minicpm_o, omni-video, openclaw, orchestrator,
scripts, stt, threejs, tts, video-use, vlm, web-fetch, web-search
```
相比测试里写的 20 个，**实测多出的 4 个**：`vlm`（我 a7ef9b2 注册的视觉适配器）、`desktop-touch`、`omni-video`、`video-use`（后续接入的 MCP/视频适配器）。

### 2.2 修复方案（安全、零歧义、已核实）
1. `tests/test_fabric_hub.py` 的 `_EXPECTED_ENGINES` 集合补 4 行：
   ```python
   "vlm",          # 视觉理解适配器（a7ef9b2 注册）
   "desktop-touch",# 桌面触控 MCP
   "omni-video",   # 全模态视频适配器
   "video-use",    # 视频操作 MCP
   ```
2. `AGENTS.md` 基线表"适配器总数 20"→**24**（与实测一致）。
3. 为防再次漂移，建议在 `_EXPECTED_ENGINES` 上方注释强调"新增引擎在此追加一行"。

> 此项为**测试常量/声明同步**，已用 `health_report()` 实测核对，不编造数字。是否由我执行待你拍板（见 §6）。

---

## 3. 适配器注册实况（单一真相源实测）

`FabricHub().health_report()` → `total=24, live=20`。
- 与 memory 记录一致：裸 `_ADAPTERS` 19 + orchestrator 自动注册 + 后续 MCP/视频/触控适配器 = 24。
- `AGENTS.md` 当前未提交版本写"适配器总数 20"**已过时**（没算 MCP 引擎），应随 §2.2 一并改为 24。

---

## 4. "路由预测器"方案切入点评估（用户原计划下一步）

目标：把"十大模型"里最后没用上的 **DNN/MLP** 借鉴到 AOS 真实痛点——从结构化 Trace 学 `P(成功 | 能力, 引擎, 档位)`，让路由从写死的偏好表进化成"越用越准"。

**关键发现（影响方案地基）**：
- `registry.py` 当前未提交改动只是删无用 import，**无冲突**，可在其上新增 `ROUTE_STRATEGY="learned"`。
- 但 **`route()` 执行完不记录任何结果**，且 `OperationTracer` 的 Trace **只在内存、不落盘**——所以现在根本没有"路由维度"的可学习数据。
- 因此落地顺序必须是：
  1. **先加 `RouteOutcomeStore`**：给 `route()` 每次尝试落一条 JSONL（capability / engine / tier / ok / 耗时）。这是路由维度的"结构化 Trace 落盘"，也是第 8 条理念（白盒才可进化）的真实落点。
  2. **再上 `RoutePredictor`**：numpy 手写 MLP（单隐层 + sigmoid，SGD），从落盘结果学成功概率。
  3. **新增 `learned` 策略**：排序用预测分；**数据不足/无模型时诚实回落 `preference`**，绝不瞎编。

无 GPU、只用已装 numpy、不破坏现有 `preference/cost/latency/quality` 策略——与现有架构正交。

---

## 5. 已知遗留（不在此次范围）

- `tests/test_database.py` / `test_memory.py`：legacy 失败（no such table），memory 已记"勿误修"。
- 后台覆盖率任务 `O1cajk` 曾计划回填 AGENTS.md §0.5，现已部分落地（测试数 480），覆盖率% 仍待 `AOS_BASELINE_HEAVY=1` 实测。

---

## 6. 建议的下一步（按依赖顺序）

| 步骤 | 动作 | 是否需你确认 |
|------|------|------|
| A | 修 2 个红测试（§2.2 精确 diff）+ AGENTS.md 适配器总数 20→24 | 我可直接做（已核实） |
| B | `.gitignore` 追加 `coverage.json`、`.arts/` | 我可直接做 |
| C | 把 14 个良性未提交改动 + 2 新测试 **提交**（本地 commit，由你主机 push） | 需你确认提交范围 |
| D | 上路由预测器（先 OutcomeStore 落盘 → 再 MLP 预测器 → learned 策略） | 需你拍板后我动手 |

**置信度**：版本控制/测试/注册数结论均来自实测，置信 **高**；路由预测器为方案评估，待拍板。
