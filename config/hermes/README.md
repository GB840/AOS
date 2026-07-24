# config/hermes/ —— Hermes 子系统本地配置与运行时产物

本目录服务于 **Hermes Agent 子系统**（legacy 大脑桥接）。AOS 的 Python 包
**不 import 本目录**；真实进程内配置来自 `src/utils/config.py`。

| 内容 | 类型 | 说明 |
|---|---|---|
| `config.yaml` | 配置 | Hermes 模型上下文长度等（仅 `model.context_length`） |
| `SOUL.md` / `memories/USER.md` | 运行时 | Hermes 人格 / 用户记忆快照 |
| `auth.lock` / `*.lock` | 运行时锁 | 本地会话锁，不应入库 |
| `.skills_prompt_snapshot.json` | 运行时 | 技能提示词快照 |
| `sessions/*.json` | 运行时 | 请求 dump，属临时产物 |
| `lsp/` | 工具 | 本地 LSP（pyright 等）二进制 |

> 建议：除 `config.yaml` / `SOUL.md` 外，其余（锁、快照、sessions dump、lsp 二进制）
> 属本地运行时产物，应在 `.gitignore` 中排除，避免污染仓库。
> 与根目录 `configs/`（基础设施配置）命名相近但职责不同，请勿盲合。
