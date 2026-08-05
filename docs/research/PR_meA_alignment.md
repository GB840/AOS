# PR：feat(MEA) 长程任务三权分立对齐 —— AuditorGate + 已验证里程碑层 + 真实 EnvironmentAuditor 接线

> 本文件既是 PR 说明，也是你主机建 PR 的 `--body-file` 内容（见文末「主机执行命令」）。
> 诚实分级：**②级**（代码改动 + 离线单测实证）。③级真 LLM 端到端沙箱无 GPU/麦克风，未跑、不谎报。

## 背景与选型（已核验，非编撰）

贴来的 `LongHorizon-Harness / MEA 三角色循环` 资料经 WebSearch 交叉验证为**真实**：
- arXiv:2608.01964（阿里高德 DreamX Team，2026-08）+ GitHub `AMAP-ML/LongHorizon-Harness`；
- Qwen 3.7-Plus / Claude Opus 4.7 官方可查；License **MIT**（母纲友好）。

**选型结论（融合，不甩选择题）**：不引入其作依赖——它是「跑在 Claude Code 之上的执行底座」，与 AOS 自身是**同类竞品**，引入即成「OS 套 OS」，违反自研内核定位 + 反缝补铁律。正确动作是把 MEA 的「**显式 verified state + 只读 auditor gate**」模式补进 AOS 现有层（run_state_store / autopilot），**不新建组件**。

## 交付内容（commit 84c5934..07ee391，共 7 个，9 文件 +691/-4）

| 文件 | 作用 |
|---|---|
| `src/kernel/auditor.py`（新） | `EnvironmentAuditor`：只读核查**文件/日志等环境事实**，支持 `verify` 规格 `file`/`files`/`contains`(正则)；无 verify 默认放行（向后兼容），未知类型跳过不阻断 |
| `src/kernel/run_state_store.py` | **Gap2**：`save_checkpoint` 加默认关闭 `_AUDITOR` 钩子，未通过则拒绝覆盖旧快照；<br>**Gap1**：新增 `verified_milestones` 表（与 `runs.state` 进度快照物理分离）+ `propose_milestone`（经审计才写入）+ `get_verified_milestones` |
| `src/kernel/autopilot.py` | `run()`/`resume_run()` 入口经 `_maybe_install_default_auditor()` 自动 `set_auditor`，仅未注册时接入、测试已 set 不覆盖、失败静默放行绝不阻塞 run |
| `AGENTS.md` | 补 §0.0.5.A 选型铁律执行记录 + 订正 DBX 注释；去重误粘贴的重复段 |
| `scripts/run_full_coverage.sh` | 补全本机/CI 全量覆盖率落地途径（建 venv→装依赖→跑→读数→避坑） |
| `docs/research/aos_mea_alignment_2026-08-05.md` | MEA 对齐审计（同构对照 + 真实 gap + 落地判断） |

## MEA 三角最终态（全②级收口）

| MEA 角色 | AOS 对应 | 状态 |
|---|---|---|
| Manager（目标+已验证里程碑，不碰环境） | `autopilot.run` + `verified_milestones` 层 | ✅ |
| Executor（每轮全新上下文） | `_execute` 每轮新建 `OrchestrationChiplet`（经代码核查已实现） | ✅ |
| Auditor（只读验证，仅通过才写状态） | `EnvironmentAuditor` + `AuditorGate` + `propose_milestone` | ✅ |
| 状态持久化（跨上下文续跑） | `run_state_store` sqlite + `resume_run` | ✅ |

## 测试实证

- MEA 专属测试：`test_environment_auditor.py`(17) + `test_verified_milestones.py`(6) + `test_auditor_gate.py`(5) = **28 项②级全绿**；
- 全硬化套件（含上述 + brain逻辑/限流/混沌/双轨/蒸馏/fabric_chat/crawl/bidding）合跑 **117 passed, 1 skipped**；
- 覆盖率（沙箱可复现局部口径，仅 MEA 触及模块）：`auditor.py` **95%**、`run_state_store.py` 80%+、触及模块合计 **76%+**（远超 #16 的 50% 门槛）。

## 诚实边界 / 已知限制

- **③级未做**：真 LLM 端到端需在 GPU 主机跑 `AOS_RUN_REAL_TESTS=1` 的 `test_self_evolution_real*` 等，沙箱无 GPU 不谎报。
- **全局全量覆盖率数字缺失**：沙箱存在「单例污染 + fork 资源耗尽」（本次实测 11 文件合跑 9 分钟被 kill、全量 collect 直接 fork 失败），无法产出可信全局数字。真实全局数字请在你本机/CI 跑 `scripts/run_full_coverage.sh`（已交付，含 Windows/PowerShell/Linux 三套路径）。
- **非阻断遗留**：任务级 `verify` 规格化——各 run 在自己产出的 checkpoint/milestone 里声明「完成靠哪个文件/日志佐证」，框架已就位，调用方按需填 `verify` 字段即可，非代码债。

## 主机执行命令（push 与建 PR 由你主机执行，AI 不代推）

```bash
# 1) 进入仓库根（已配 SSH origin=git@github.com:GB840/AOS.git）
cd /path/to/AOS

# 2) 推送 feature 分支（远程 master 已在 1a6d6b0，本分支 07ee391 为其线性后继，纯 ff）
git push origin feature/infra-setup

# 3a) 有 gh 则直接建 PR（本文件即正文）：
gh pr create --base master --head feature/infra-setup \
  --title "feat(MEA): 长程任务三权分立对齐 —— AuditorGate+已验证里程碑层+真实EnvironmentAuditor接线" \
  --body-file docs/research/PR_meA_alignment.md

# 3b) 无 gh 则用 GitHub API（把 <TOKEN> 换成你的 GitHub PAT，需 repo 权限）：
curl -X POST -H "Authorization: Bearer <TOKEN>" -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/GB840/AOS/pulls \
  -d '{"title":"feat(MEA): 长程任务三权分立对齐","head":"feature/infra-setup","base":"master","body":"见仓库 docs/research/PR_meA_alignment.md"}'
```

> 注：远程 `master` 与 `feature/infra-setup` 当前均停在 `1a6d6b0`；推送后 feature 前进到 `07ee391`，PR diff = 这 7 个提交。GitHub 常 `Empty reply from server`（国内可达性问题），若 push 失败改用 `git@github.com:GB840/AOS.git` 的 443 SSH 或重试。
