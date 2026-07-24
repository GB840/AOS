# configs/ —— AOS 基础设施与部署配置

本目录存放**部署 / 基础设施级**配置，由 docker-compose、PostgreSQL、Temporal
等外部工具消费。**AOS 的 Python 包并不 import 本目录**——进程内真实配置来自
`src/utils/config.py`（从 `.env` / 环境变量加载）。

| 文件 | 谁消费 | 用途 |
|---|---|---|
| `global.yaml` | detect_env.sh / 部署脚本 | 服务连接（postgres/redis/temporal）、技能系统、Hermes/DeerFlow/子智能体路径 |
| `postgres/init.sql` | PostgreSQL 容器初始化 | 库 / 表 / 审计库建表 |
| `temporal/development-sql.yaml` | Temporal 开发集群 | 时序数据库配置 |

> ⚠ 与根目录 `config/`（Hermes 子系统配置 + 运行时产物）**命名相近但职责不同**，
> 请勿盲合。二者都不被 AOS Python 包 import；真实配置模块是 `src/utils/config.py`。
