# AOS 开源标准对照索引（Open-Standard Contrast Index）

> 本目录（`references/standards/`）存放 AOS 采用的三个行业开放标准的**真实完整源文件**，
> 于 2026-07-13 从上游仓库克隆（depth 1），用于与 AOS 根 `AGENTS.md` 逐条对照，
> 杜绝"凭记忆复述、未经原文件验证"的悬空规则。

## 1. 三个真实开源源（已落地，可逐字对照）

| 标准 | 本地路径 | 上游仓库 | 克隆基准 commit | 授权真实状态 |
|------|----------|----------|-----------------|--------------|
| AGENTS.md 开放标准（官网源码 + 规范样本） | `references/standards/agents-md/` | github.com/agentsmd/agents.md | `d1ac7f063d20e70015ed6732664049ae4ba9d74e` | ✅ MIT（含 LICENSE 文件，OpenAI 2025） |
| Qoder-Rules 规范库（core/quality/architecture + tools/spec-lint.py） | `references/standards/qoder-rules/` | github.com/lvzhaobo/qoder-rules | `144ab591e4abe774fdfd93a4fad1bc349c3c45cf` | ⚠️ 仓库未随附 LICENSE 文件；AOS 仅引用规则文本作工程规范参考，商用请向上游确认 |
| Karpathy 四原则（CLAUDE.md / SKILL.md / .cursor/rules） | `references/standards/andrej-karpathy-skills/` | github.com/multica-ai/andrej-karpathy-skills | `2c606141936f1eeef17fa3043a72095b4765b9c2` | ⚠️ SKILL.md frontmatter 声明 `license: MIT`，但仓库根无 LICENSE 文件 |

**诚实标注**：后两者上游未随仓库提供 LICENSE 文件。AOS 引用其规则文本作为工程规范参考，
不主张对其代码的再分发权利；如需商用请向上游确认授权。

## 2. 对照映射表

### 2.1 AOS 命门哲学 ↔ 标准
| AOS 原则 | 对应真实标准条目 | 真实源路径 |
|----------|------------------|------------|
| 万物为我所用 / 不绑定 | Qoder 规则2「复用现有代码和 API」、规则13「只用真实存在的库」 | `qoder-rules/core/requirements-spec.zh-CN.md` 规则2 / 13 |
| 端云合作 / 一样用不了就换别样 | AGENTS.md「云端用不了就本地」哲学；本项目 `route()` 已实现跨供给方运行时故障转移 | `agents-md/README.md`；`src/core/fabric/registry.py` / `src/kernel/plugins/fabric_hub.py` |
| 零成本可跑（不充值也能端到端） | Qoder 规则3「最小化新增依赖」、规则13「只用真实库」 | `qoder-rules/core/requirements-spec.zh-CN.md` 规则3 / 13 |

### 2.2 AOS 诚实纪律 ↔ Karpathy 四原则
| AOS 纪律 | 对应 Karpathy 原则 | 真实源路径 |
|----------|-------------------|------------|
| 先思考再编码 | 原则1 Think Before Coding | `andrej-karpathy-skills/CLAUDE.md` §1 / `SKILL.md` §1 |
| 改动最小化（Surgical） | 原则3 Surgical Changes + Qoder 规则5「仅修改请求的内容」 | `andrej-karpathy-skills/CLAUDE.md` §3；`qoder-rules/core/requirements-spec.zh-CN.md` 规则5 |
| 可验证目标 / 提交必核验 hash | 原则4 Goal-Driven Execution（写复现测试→让它过） | `andrej-karpathy-skills/CLAUDE.md` §4 |
| 简洁优先 | 原则2 Simplicity First | `andrej-karpathy-skills/CLAUDE.md` §2 |

### 2.3 AOS 质量门 ↔ Qoder 测试规范
| AOS 质量门 | 对应 Qoder 测试规则 | 真实源路径 |
|------------|---------------------|------------|
| 提交前 pytest 全绿 / 新功能带测试 | 规则1「测试完整性」、规则3「测试分层」 | `qoder-rules/quality/testing-spec.zh-CN.md` 规则1 / 3 |
| 覆盖率基线不倒退 | 规则2「覆盖率目标」 | `qoder-rules/quality/testing-spec.zh-CN.md` 规则2 |
| 真实可跑不弄虚 | 规则10「确保代码成功编译」、规则6「验证 API 存在」、规则13「只用真实库」 | `qoder-rules/core/requirements-spec.zh-CN.md` 规则10 / 6 / 13 |

## 3. 用开源工具自检（可选交叉验证）
Qoder-Rules 自带 `tools/spec-lint.py`，可对代码做规范检查：
```bash
python references/standards/qoder-rules/tools/spec-lint.py --target-dir ./src --spec-dir ./references/standards/qoder-rules/core
```
AOS 主质量门仍是自写 pytest；此工具作为可选交叉验证，不在提交强制门内。

## 4. 权威顺序
**运行时代码事实 > AOS `AGENTS.md` > 本目录开源标准原文。**
开源原文是"对照基准"，`AGENTS.md` 是"本项目唯一执行规则源"；二者冲突以 `AGENTS.md` 与本仓库代码为准。
