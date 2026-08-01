# 生命体操作系统 · 落地构建计划（LIFEFORM_OS_BUILD_PLAN）

> 配套文件：[`LIFEFORM_OS_WHITEPAPER.md`](LIFEFORM_OS_WHITEPAPER.md)（白皮书 v2 核验修正版）
> 事实底座：[`docs/research/lifeform_os_reference_audit.md`](research/lifeform_os_reference_audit.md)
> 宪法上位法：[`AGENTS.md`](../AGENTS.md)
> 创建日期：**2026-07-26**　状态：路线图 v1

---

## 0. 这份计划怎么读、怎么算"做完"

白皮书第九章给了 P0-P4 五期目标，本文件把它们**展开成可执行的工程动作**：每期都明确——要动哪个真实文件、建什么新模块、验证门槛是什么、做完的真机命令是什么。

**诚实度三级门槛（每期交付前必须自报属于哪一级，禁止跳级宣称）：**

| 级 | 含义 | 判定方式 |
|---|---|---|
| ① 代码就绪 | 文件落地、可 `grep` 到、能 `import` | `python -c "import <module>"` 不报错 |
| ② 单元/芯粒验证 | 有单测覆盖、mock 跑通关键路径 | `pytest tests/test_xxx.py` 绿 |
| ③ 端到端真验 | 真 LLM + 真主机跑出可复核证据 | 真机命令产出可复现日志/产物 |

**最高纪律**：凡只到 ①/② 的，文档与汇报一律写"未端到端验证"，绝不写"跑通"。这是 AOS 宪法级红线（白皮书第十章第 8 条）。

**执行顺序硬约束**：P0 必须先于 P1-P4 拿到一个真 LLM 端到端证据。原因见白皮书第八章——"端到端自进化从未验证"是最大空心，不先补这个，后面 P1/P2/P3 都是在没有地基的情况下盖楼。

---

## 1. 与单创OS 共用内核的切换机制（贯穿所有期的底座）

不另起仓库、不另起平行目录。所有新增代码进现有 `src/`，通过**人格配置 + 运行模式**切换"两张脸"。

### 1.1 已存在的能力（可直接复用，不必新造）

`src/core/fabric/persona.py` 已实现：
- `DEFAULT_PERSONA`（代码内置默认，小元人设）
- `load_persona(user_id)` / `save_persona(user_id, patch)`：用户专属 `personas/{user_id}.yaml` 覆盖全局 `default.yaml`
- `ensure_default_template()`：从 `references/persona.default.yaml` 复制带注释模板（单一真相源，可进 git）

这正是"一张脸一套文件、另一张脸另一套文件"的天然落点。

### 1.2 需要补的切换开关（P0 前先做，约 30 行改动）

在 `DEFAULT_PERSONA` 增加两个字段，并在加载处消费：

```python
# persona.py · DEFAULT_PERSONA 增加
"os_mode": "lifeform",          # lifeform | singlechuang
"face": {                        # 两张脸的差异点
    "lifeform":  {"tagline": "我的数字生命体伙伴", "enable_layers": "L0-L7"},
    "singlechuang": {"tagline": "多租户自主创业 OS", "enable_layers": "L0-L8"},
},
```

加载时根据 `os_mode` 决定：
- `lifeform` → 启用 L0-L7（自用、单实例、深度），`companion.py` 在场感全开
- `singlechuang` → 启用 L8 商用面（多租户隔离、`web/tenant` + BYOK、`src/kernel/danchuang/`）

**不新增任何平行模块**。差异只在"启用哪些层 + 走哪套 Web 前端"，内核完全一致。

### 1.3 运行模式读取方式

优先级：`环境变量 AOS_MODE` > `persona.yaml 的 os_mode` > 代码默认 `lifeform`。
- 生命体OS 自用：`AOS_MODE=lifeform python -m kernel.autopilot "..."`
- 单创OS 商用：由 `web/tenant` 按租户 `os_mode` 字段决定，不靠全局环境变量。

---

## 2. P0 · 补 L5 端到端证据（最大空心，最先做）

> 白皮书定位：P0 是当务之急。没有这一条，整个"自进化生命体"叙事塌方。

### 2.1 目标

产出**一次可复现的真 LLM 任务**记录，证明闭环："执行一轮 → 真失败 → 反思 → 下一轮因反思而变好"。

### 2.2 已具备的接线（确认过，不必新造）

- `src/kernel/autopilot.py` 已 `from kernel.evolution_distiller import EvolutionDistiller` 并接入 `CausalModel`
- `src/kernel/opc_loop.py` 已实现 `STAGE_REGISTRY` + Meta-Trace 回流：`每轮失败教训写入 Meta-Trace，下轮分析阶段自动注入`
- 已有测试 `tests/test_autopilot_causal_reflection_e2e.py`（mock 模式跑通）

**结论**：代码是真的，缺的是"真 LLM + 真主机"下的端到端跑通证据。

### 2.3 具体动作

| 动作 | 文件 | 级别 |
|---|---|---|
| 写一个真机验证脚本 `examples/lifeform_self_evolve_demo.py` | 新建 | ①→② |
| 脚本逻辑：给定同一任务，第 1 轮故意用弱参数/坏检索 → 必失败；第 2 轮注入第 1 轮 Meta-Trace 教训 → 成功 | 新建 | ② |
| 跑真机（需主机 aos venv + 真实可用 LLM key），记录 `runs/self_evolve_<ts>.jsonl` | 真机 | ③ |
| 产物含：两轮完整 trace + 第 1 轮失败原因 + 第 2 轮路由/规划 diff（证明"变好"可 diff） | 真机 | ③ |

### 2.4 验证门槛（必须真机，沙箱不行）

```powershell
# 主机 PowerShell（非沙箱；沙箱 Python3.14 跑重型链会假失败）
cd D:\AOS
& "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" `
   -m kernel.autopilot "检索并评估一个真实存在但冷门的开源语音模型，给出是否适合 Windows 的结论"
# 预期：第 1 轮失败轨迹落盘 → 第 2 轮读取 Meta-Trace → 成功产出评估
# 验收：runs/ 下出现 self_evolve_*.jsonl，且 diff 显示第 2 轮检索策略与第 1 轮不同
```

**诚实标注**：P0 完成 = 拿到 ③ 级证据。若真机因 key/网络受限只跑出 ②，则文档写"L5 端到端在 mock 下验证通过，真 LLM 下 ③ 未验证"，**绝不许写跑通**。

### 2.5 防御性测试

- `tests/test_autopilot_causal_reflection_e2e.py` 增补断言：Meta-Trace 在第 2 轮被实际消费（不只写入）
- 门禁：CI 跑 mock 版保证 ② 常绿；③ 靠真机手动跑 + 产物留档

### 2.6 ✅ 执行结果（2026-08-02，已真跑，非计划）

**照白皮书 P0 实际执行，已产出可复现的真 LLM 闭环证据：**

- 脚本：`examples/lifeform_self_evolve_demo.py`（直接用现有 `kernel.autopilot._reflect_and_redesign` + `SearchAdapter` + `EvolutionDistiller`，零新造）
- 产物：`runs/self_evolve_20260802_000754.jsonl`、`runs/distill_20260802_000754.jsonl`
- Meta-Trace 教训真落盘：`_traces/reflection_memory.jsonl`（ts=2026-08-02T00:10:57，failed=web.search）

**闭环实测（全程真实组件）：**
| 阶段 | 结果 |
|---|---|
| Round1 搜索 | `ok=False / is_real=False`（anysearch+baidu+ddg 临时停用，模拟源不可用 → 真失败） |
| 反思（真 LLM ag2/智谱） | `engine_hint=anysearch`，`causal_hints={"web.search":"anysearch"}`（来自真实蒸馏器证据：anysearch 11/11、bing 2/9） |
| Round2 搜索（anysearch） | `ok=True / is_real=True`（真实 5 条结果） |
| 教训落盘 | `_save_lesson` 写入 `_traces/reflection_memory.jsonl`（失败即训练真实发生） |

**诚实判定：`end_to_end_passed=true`，诚实级 = ③ 真 LLM 反思 + 真搜索调用 + 真实蒸馏器证据。**
**范围边界（不夸大）**：本验证证明「单次失败 → 反思换引擎 → 下一轮变好」机制真实可复现；尚未覆盖「任意任务全自动多轮自进化」的全景验证，后者仍是后续增强项，不在此宣称已验。

复跑：`AOS_ZHIPU_OPTIN=1 python examples/lifeform_self_evolve_demo.py`（依赖 `.env` 真实 key，已就位）。

---

## 3. P1 · 补 L0 生命状态内核（第二优先，唯一近乎全缺的层）

> 白皮书定位：L0 是九层里**唯一几乎完全缺失**的一层。现有人设没"生命状态"。

### 3.1 目标

新建 `src/kernel/life_state.py`，定义生命状态向量 `energy / mood / focus / debt`，并让状态**真实影响路由与决策**（不是展示用）。

### 3.2 具体动作

| 动作 | 文件 | 级别 |
|---|---|---|
| 定义 `LifeState` 数据类（4 维 + 时间戳 + 衰减规则） | `src/kernel/life_state.py` 新建 | ① |
| 状态衰减函数：`energy` 随连续推理递减、`debt` 随未完成/失败任务递增、`focus` 随任务切换重置 | 同上 | ①→② |
| 接入 `autopilot`：当 `energy < 阈值` 时自动降档（选更轻模型/缩短检索） | 改 `autopilot.py` | ② |
| 接入 `persona`：L0 状态写入 `persona.yaml` 同目录 `life_state.json`（每用户一份） | 改 `persona.py` | ② |
| 写单测 `tests/test_life_state.py`：衰减/阈值/持久化全绿 | 新建 | ② |
| 真机留档：连续跑 10 轮任务，导出 `energy/debt` 曲线截图存 `docs/research/` | 真机 | ③（可选但鼓励） |

### 3.3 状态影响路由的诚实门槛

必须证明"状态真的影响了决策"，否则只是表演。验收：单测构造 `energy=0.1` 与 `energy=0.9` 两种状态跑同一任务，断言前者选轻型引擎、后者可选重型——断言落 `tests/test_life_state.py`。

### 3.4 与现有模块的关系

- `src/kernel/semantic_state.py` 已存在 → `LifeState` 复用其持久化基类，不重造
- `src/kernel/isolation/` 已有配额散落逻辑 → P1 仅引用，不在本期权收口（收口留 P3 生长约束执行器）

---

## 4. P2 · 补 L3 灵魂层（价值排序 + 情感影响决策）

> 白皮书定位：第二个大缺口。现在"人格"只是提示词表演，不参与决策。

### 4.1 目标

- **价值排序器**：多目标冲突时有确定取舍顺序（如"安全 > 准确 > 速度 > 成本"）
- **情感状态机**：情绪**真实影响**决策权重（低落时降低冒险权重），非展示

### 4.2 已具备 + 外部参考（只借鉴不引码）

- `src/kernel/compliance.py` ②、`src/kernel/approval/` ② → 排序器的"硬约束"来源
- 外部参考 `acgs-ai/acgs-lite`（AGPL-3.0）→ **只读借鉴其宪法治理结构，禁止引码、禁止 link**（见审计表）

### 4.3 具体动作

| 动作 | 文件 | 级别 |
|---|---|---|
| 定义 `ValueHierarchy`：有序价值列表 + 冲突解析函数 | `src/kernel/soul/value_hierarchy.py` 新建（目录 `soul/` 新建） | ① |
| 定义 `EmotionState`：mood 维度 + 对决策维度的权重映射表 | `src/kernel/soul/emotion_state.py` 新建 | ① |
| 把 L0 的 `mood` 接入 `EmotionState`，输出"当前冒险容忍度" | 改 `life_state.py` 关联 | ② |
| 在 `autopilot` 决策点注入价值排序（副作用操作先过 `ValueHierarchy`） | 改 `autopilot.py` | ② |
| 单测 `tests/test_soul.py`：构造冲突场景，断言排序器输出确定；构造低落情绪，断言冒险权重下降 | 新建 | ② |
| **AGPL 合规门禁**：CI 扫描 `soul/` 不得 `import acgs` 任何符号 | CI | ② |

### 4.4 诚实门槛

"情感影响决策"必须有可 diff 的证据：单测构造同一任务在 `mood=excited` vs `mood=sad` 下，断言规划器选了不同风险等级的动作。没有这个断言，L3 只到 ①。

---

## 5. P3 · 补 L7 分形派生（繁殖 + 生长约束）

> 白皮书定位：第三个大缺口。现在有"隔离"没有"繁殖"。芯粒是人写的，不是系统派生的。

### 5.1 目标

- **分形派生器**：母体按自相似规则生成结构缩微的子体（芯粒 = Adapter 实例 + 裁剪状态 + 独立 mem 命名空间）
- **生长约束执行器**：硬编码 3 代 / 配额 ×1/3 / 兄弟数 8 / 写·联网·花钱需审批

### 5.2 已具备

- `src/core/fabric/adapter.py`（芯粒抽象，③）
- `src/kernel/isolation/`（子进程 crash boundary，②）
- `src/kernel/self_harness.py`（自检 harness，②）→ 子体须通过母体同一套自检

### 5.3 具体动作

| 动作 | 文件 | 级别 |
|---|---|---|
| `FractalSpawner.spawn(parent, tier)`：生成裁剪版状态 + 独立 mem 命名空间 | `src/kernel/fractal/spawner.py` 新建 | ① |
| `GrowthGuard`：代数计数、配额衰减、兄弟数排队、审批触发 | `src/kernel/fractal/growth_guard.py` 新建 | ① |
| 生长约束**硬编码常量**（不可配置为无限）：`MAX_GEN=3, QUOTA_DECAY=1/3, MAX_SIBLINGS=8` | 同上 | ① |
| 子体 spawn 后跑 `self_harness` 自检，失败即销毁并记录 | 改 `self_harness.py` 接 spawner | ② |
| 单测 `tests/test_fractal.py`：派生到第 4 代被拒、配额第 3 代=11%、兄弟超 8 排队、写操作触发 approval | 新建 | ② |
| 真机留档：`kill -9` 任一子进程，母体主环存活 + 记死亡事件 | 真机 | ③ |

### 5.4 诚实门槛

"繁殖不是癌症"必须有真机证据：单测覆盖代数/配额/兄弟数，真机覆盖"子进程崩不影响母体"。缺任一项，L7 只到 ②。

---

## 6. P4 · 生态与商用面收口

> 白皮书定位：技能市场 + 多租户商用面。

### 6.1 目标

- 技能市场真能注册/检索/安装（`src/kernel/skill_registry.py` 已 ②）
- 多租户商用面与生命体OS 共用内核、按 `os_mode` 切换（见 §1）

### 6.2 具体动作

| 动作 | 文件 | 级别 |
|---|---|---|
| 技能市场：补 `install`/`uninstall` 真路径 + 许可扫描（AGPL 拒绝上架） | `src/kernel/skill_registry.py` | ② |
| 经验共享 `experience_sharing.py`（现 ①）补真实回流测试 | 改 + 测 | ② |
| 生态调度 `ecology.py`（现 ①）补一个真实 MCP 双向接入样例 | 改 + 测 | ② |
| `web/tenant` 按租户 `os_mode` 渲染商用面（复用 §1 切换） | `web/tenant` | ②→③ |
| BYOK 密钥层（已 ②）接 tenant 路由验证 | 改 + 测 | ② |

### 6.3 诚实门槛

P4 多数为 ②（商用面真机需部署环境）。凡未真机部署验证的，标注"③ 未验"。

---

## 7. 执行顺序与依赖总览

```
P0 (L5 端到端证据)  ← 必须最先，地基
 │
 ├─→ P1 (L0 生命状态)      ← P0 之后即可，独立
 │     │
 │     └─→ P2 (L3 灵魂层)   ← 依赖 P1 的 mood 状态
 │
 └─→ P3 (L7 分形派生)      ← 与 P1/P2 并行可行，独立
       │
       └─→ P4 (生态商用)    ← 最后收口
```

**§1 的切换机制（persona os_mode）必须在 P0 前落地**（约 30 行），否则 P4 无法切换两张脸。

---

## 8. 测试与提交纪律（每期通用）

沿用 AOS 现有工程纪律（已验证有效）：

1. **每期必有单测**：新建 `tests/test_<module>.py`，跑 `pytest` 全绿再提交。
2. **真机验证不虚**：③ 级证据必须在主机 aos venv 真跑（沙箱 Python3.14 跑重型链会假失败，不代表项目缺依赖）。
3. **提交前**：`git log -1` + `git log origin..HEAD` 核验 hash；heredoc 含 ASCII 引号改用中文引号『』。
4. **GitHub push**：国内常 `Empty reply`，优先 SSH：`git@github.com:GB840/AOS.git`；22 不通走 443 SSH。
5. **诚实标注**：每期交付物在白皮书附录 A 的对应层更新 ①②③ 状态，**禁止跳级**。
6. **外部依赖引入前**：先 WebSearch 核实真实性/许可（本次已建 `lifeform_os_reference_audit.md` 为底座，新增引用须补进该表）。

---

## 9. 完成判据（全部五期做完后的"生命体OS 真的活着"清单）

| "活着"判据（白皮书执行摘要） | 由哪期补齐 | 完成信号 |
|---|---|---|
| 有边界 | 已有 + P3 生长约束 | 配额耗尽被拒日志可查 |
| 有代谢 | 已有（TTL/生命周期） | 淘汰记忆/死亡粒子记录可查 |
| 有稳态 | 已有（免疫/降级） | 扰动后回基线 |
| 有目标 | 已有（autopilot/opc） | 长程任务自主推进 |
| 有进化 | **P0** | 真 LLM 下"一轮变好一轮"可复现 |
| 能繁殖 | **P3** | 派生子体通过母体自检 + 生长约束生效 |

**最终诚实总结**：L1/L2/L6 本来就是真的；P0 把 L5 从"代码真验证空"补到"有端到端证据"；P1/P2/P3 把 L0/L3/L7 从"真缺口"补到"代码就绪+单元验证"。是否达到 ③ 级，每期按 §0 门槛如实自报。
