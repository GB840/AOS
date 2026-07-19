# 接入评估：AgentScope 作为 AOS 可选编排后端

> 结论：**可用，但必须隔离**（作为可选编排后端候选，绝不作为内核）。
> 评估依据：2026-07-19 全网交叉核实（官方文档 / GitHub README / deepwiki / 科技媒体）。

---

## 1. 当前状态与许可证

| 项 | 结论 | 置信 |
|---|---|---|
| 仓库 | `github.com/agentscope-ai/agentscope`（已从 modelscope 迁移至独立组织） | ✅ 已确认 |
| 许可证 | **Apache 2.0**（README 明示） | ✅ 已确认 |
| 活跃度 | 持续迭代，官网宣发 2.0 大版本信号 | ✅ 已确认（2.0 口径待稳定） |

## 2. 是否硬绑定阿里云 SDK —— **不绑定**

- 模型层是开放包装器体系：`OpenAIChatModel` / `DashScopeChatModel` / `GeminiChatModel` / `OllamaChatModel` 并列。
- **可纯本地、离线、无阿里云账号运行**：明确支持 Ollama（默认 `localhost:11434`）及任意 OpenAI 兼容端点（vLLM / LocalAI）。
- 模型适配层开放，非锁死通义；DashScope 仅是可选之一。

## 3. 安装与最小 API

```bash
pip install agentscope        # Python >= 3.10
# 可选：agentscope[full]（模型 API+工具）/ agentscope[dev]
```

核心抽象（基于真实 API）：

```python
from agentscope.agent import ReActAgent
from agentscope.model import OllamaChatModel   # 本地，无阿里云
from agentscope.pipeline import MsgHub
from agentscope.message import Msg

a = ReActAgent("Alice", model=OllamaChatModel(model_name="llama3"))
b = ReActAgent("Bob",   model=OllamaChatModel(model_name="llama3"))
async with MsgHub([a, b], announcement=Msg("system", "Introduce.", "system")):
    await a(); await b()
```

## 4. 与 AOS 的契合度

**可用但需隔离（作为可选编排后端候选）。**

| 优势 | 风险 |
|---|---|
| Apache 2.0、开放模型层、可离线 | ① **API 动荡**：2.0 大版本重构信号，接入层须抽象隔离 |
| 多智能体编排（MsgHub / Pipeline / Debate）开箱即用 | ② 治理受阿里路线主导 |
| 补 AOS 的 agent 协作样板 | ③ 与 FabricHub 路由内核功能重叠——须明确「只编排、不替换内核」 |

## 5. 接入建议（AOS 方式实现）

1. **只接编排，不接内核**：用适配层包裹 AgentScope，仅暴露 `orchestrate(...)` 接口，
   AOS 的 FabricHub 统一路由 / 反思闭环 / 白盒蒸馏不变。
2. **隔离边界**：所有 `import agentscope` 收口在 `kernel/plugins/agentscope_bridge.py`，
   启用经 env（如 `AOS_AGENTSCOPE=1`），缺失依赖时优雅跳过，绝不拖垮枢纽。
3. **复用而非依赖**：把 AgentScope 的 MsgHub / Pipeline 当作 AOS 多智能体协作的
   「可选实现之一」，与现有 agnes / ag2 子进程隔离并存。
4. **不做的事**：绝不用 AgentScope 的云微调/数据飞轮替代 AOS 白盒蒸馏——
   那是 AOS 差异化的底线（黑盒微调 vs 白盒可回退）。

## 6. 待办（若推进）

- [ ] `agentscope_bridge.py` 骨架 + env 开关（隔离）。
- [ ] 与 FabricHub `system.workflow` 能力对接的接线点 PoC。
- [ ] 锁定一个稳定版本（避开 2.0 重构窗口）再正式依赖。
