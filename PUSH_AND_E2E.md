# 收尾任务清单：push 备份 + ③级真机验证

> 本文件记录「生命体层真驱动」深度复核后的收尾状态与待办。
> 诚实分级：② = 代码 + 单测可跑；③ = 真 LLM 端到端闭环。未到③级不宣称完成。

## 状态总览

| 任务 | 状态 | 证据 |
|------|------|------|
| 深度复核：生命体层真驱动运行时 | ✅ 已完成（②级） | 生产单例 31 组件装载、`failed={}`；真实磁盘闭环降档；焊接度 42/42 孤儿 0 |
| 生产路径单测 | ✅ 已完成 | `test_lifeform_production_singleton.py` + `test_lifeform_drives_runtime.py` 10/10 绿；相关回归 137 项绿 |
| git push 备份 4 个核心 commit | ✅ 已完成 | 远端 `feature/infra-setup = f6bde05`，与本地 HEAD 一致 |
| ③级真 LLM 端到端闭环 | ✅ 已完成（沙箱真 ollama） | 见第二节；用已装小模型做等价替身（沙箱内存跑不了 qwen3:8b），机制与 `qwen3:8b→qwen2.5:3b` 完全一致 |

---

## 一、git push 备份（已完成）

沙箱本次可连通 GitHub（此前网络不通的假设已不成立），已成功推送：

```text
git push origin feature/infra-setup
# 结果：107eb77..f6bde05  feature/infra-setup -> feature/infra-setup
```

- 远端确认：`git ls-remote --heads origin feature/infra-setup` → `f6bde05…  refs/heads/feature/infra-setup`
- 推上去的 4 个 commit（老→新）：
  - `107eb77` fix: start_all.sh 自适应 Python 解释器
  - `816a58c` fix: 启动脚本优先探测 managed 3.13.12 + aos venv
  - `8f249ff` feat(lifeform): 焊活生命体层——孤儿34→0，接进 autopilot 真驱动模型选择
  - `197525e` docs(whitepaper): 补「系统集成与焊接诚实状态」
  - `f6bde05` audit(deep): 深度独立复核「真驱动」——补两个诚实披露缺口 + 生产单例测试

### 本地 loose-ref 不稳定应对（已处理）

本机 `.git` 的 loose ref 跨文件系统不持久，曾导致分支 ref 丢失、remote-tracking 引用一写就丢（status 显示 `[gone]`）。已用 `packed-refs` 钉住：

- 本地分支：`refs/heads/feature/infra-setup = f6bde05`
- 远程跟踪：`refs/remotes/origin/feature/infra-setup = f6bde05`

若以后再出现 `git status` 显示 `[gone]` 或 `rev-parse refs/remotes/origin/feature/infra-setup` 报 unknown，说明 loose-ref 又丢了，恢复命令：

```bash
# 把远端真实状态重新钉进 packed-refs（先查远端真实 sha）
git ls-remote --heads origin feature/infra-setup
# 假设返回 <SHA> refs/heads/feature/infra-setup，则：
printf '%s refs/heads/feature/infra-setup\n%s refs/remotes/origin/feature/infra-setup\n' <SHA> <SHA> >> .git/packed-refs
```

> 注意：commit 已安全备份在 GitHub，loose-ref 丢失只影响本地查看/跟踪，不丢代码。

---

## 二、③级真 LLM 端到端验证（已用沙箱真 ollama 跑通）

> 当初说"沙箱无真 LLM 跑不了"——错。沙箱装了 ollama 0.32.6，且模型库里有
> `qwen3:8b`/`qwen2.5:1.5b`/`minicpm5-1b` 等。只是 5.2GB 的 `qwen3:8b` 超出沙箱内存会被
> OOM 杀，所以用两个已装的小模型做**等价替身**跑通了完整生产链路，机制与白皮书
> 原文 `qwen3:8b→qwen2.5:3b` 完全一致（picker 读 energy、回写 life_state、重载落盘）。

### 验证结果（沙箱实跑，真实 ollama）

```
=== ③级真 LLM 端到端验证开始 ===
重模型=qwen2.5:1.5b 轻模型(预期)=minicpm5-1b
[P1-高能量] energy=1.0 model=qwen2.5:1.5b gen_ok=True out='人工智能是模拟、扩展和增强人类智能的理论、方法、'
衰减后 energy=0.0 (<0.3=True)
[P2-低能量] energy=0.0 model=minicpm5-1b gen_ok=True out='嗯，用户让我用一句话介绍人工智能。首先，我需要确'
重载后 energy=0.0 重载后 picker=minicpm5-1b
✅ ③级真 LLM 端到端闭环验证通过
```

要点：两次生成都是 ollama **真实返回文本**；模型切换由 `life_state.energy` 真实驱动；
清空单例从磁盘重载后降档仍在 → 真落盘。

### 可复现命令（沙箱或你主机都行，需 ollama + 两个模型）

```bash
# 轻模型现在可由 AOS_LLM_LIGHT_MODEL 指定（已修：此前该 env 是死的、轻模型被写死 qwen2.5:3b）
# 沙箱替身：
export AOS_LLM_MODEL=qwen2.5:1.5b AOS_LLM_LIGHT_MODEL=minicpm5-1b
# 你主机首选（白皮书原文路径）：
# export AOS_LLM_MODEL=qwen3:8b AOS_LLM_LIGHT_MODEL=qwen2.5:3b
PYTHONPATH=src python scripts/real_lifeform_drive_e2e.py
```

### ⚠️ 前置关键前提（仍成立）

模型降档**仅在 autopilot 显式声明了重模型（`AOS_LLM_MODEL`）时触发**。
纯 Ollama 默认、未声明重模型时不降档，属于**合理默认而非失效**——别误判成 bug。

### 你主机照样能跑的「完整运行时」路径（可选，验证 API 层）

```powershell
$env:AOS_LLM_MODEL = "qwen3:8b"
$env:AOS_LLM_LIGHT_MODEL = "qwen2.5:3b"
cd D:\AOS; bash start_all.sh
# 另开窗口
curl http://localhost:2026/api/lifeform          # picked_now 初始 = qwen3:8b
# 连续跑任务让 energy 过 0.3 后
curl http://localhost:2026/api/lifeform          # picked_now 变为 qwen2.5:3b
```

---

## 三、已知风险与备注

1. **③级现已验证**：沙箱真 ollama 已跑通端到端闭环（机制与主机 `qwen3:8b→qwen2.5:3b` 一致），「生命体层真驱动」从②级升到③级。仍建议你在主机用 `qwen3:8b`/`qwen2.5:3b` 再跑一遍 `scripts/real_lifeform_drive_e2e.py` 做权威复现。
2. **沙箱 `.git` 网络现状**：本次可连通 GitHub；若日后又推不出去（Empty reply / 超时），优先用 SSH 443 兜底：在 `$env:USERPROFILE\.ssh\config` 写入
   ```
   Host github.com
     Hostname ssh.github.com
     Port 443
   ```
3. **系统 Python 3.14 损坏**：主机若直接用系统 `python` 跑 `start_all.sh` 会 import encodings 崩溃；脚本已改为优先探测 managed 3.13.12 + aos venv，正常无需手动干预。
