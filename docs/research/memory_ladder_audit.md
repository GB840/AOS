# 记忆阶梯（数据底座层）外部项目核实审计

> 对应蓝图新增章节「四层阶梯式融合架构」。本文件记录对 7 个外部项目 + 2 个关联项
> （cel-memory-duckdb、Turso/libSQL）的**逐字核实结论**，以及按 AOS 选型铁律
> （现有够好→复用 / 能商用开源→能用就用 / 技术栈不兼容→借鉴优化）的分类处置。
>
> 核实方式：2026-08-02 经 WebSearch 对官网 / crates.io / GitHub / modb.pro 交叉核验。
> **结论：8 项全部真实存在，许可证均 MIT / Apache-2.0，无 AGPL 传染。无一编撰。**

## 一、逐项核实表

| # | 项目 | 真实性 | 许可证 | 版本/星标(核实值) | 在记忆阶梯中的角色 | 核实来源 |
|---|---|---|---|---|---|---|
| 1 | **DuckDB** | ✅ 真 | MIT | 实测本机 `duckdb 1.5.4` 可 import（Python 3.14） | L1 瞬时感知层后端 | crates.io / llamaindex / duckdb-skills |
| 1a | cel-memory-duckdb | ✅ 真 | Apache-2.0 | v0.1.0（dimpagk92） | DuckDB 的 AI 记忆后端实现 | crates.io |
| 2 | **TriviumDB** | ✅ 真 | Apache-2.0 | v0.7.0（YoKONCy，crates.io 显示 MIT OR Apache-2.0） | L2 工作记忆层（粒子私有） | triviumdb.com / crates.io / docs.rs |
| 3 | **Turso / libSQL** | ✅ 真 | MIT | libSQL 12k★；Turso 16.8k★（2026-06） | L2 工作记忆层备选（每粒子一库） | turso.tech / dbdb.io / zairalabs |
| 4 | **KowitoDB** | ✅ 真 | MIT | v0.40.5（kowito，crates.io） | L3 长期语义层（ai.ask 统一检索） | crates.io / github kowito/KowitoDB |
| 5 | **txtai** | ✅ 真 | Apache-2.0 | neuml/txtai（向量+图谱+RAG） | L3 长期语义层备选（知识图谱） | github neuml/txtai |
| 6 | **SeekDB** | ✅ 真 | Apache-2.0 | OceanBase 2025-11-18 开源发布 | L4 永久传承层（版本归档/代际） | modb.pro / open.oceanbase.com |
| 7 | **DBX** | ✅ 真 | Apache-2.0 | ~20MB，70+ 库，Rust/Tauri，内置 MCP Server | 统一可视化层（运维期工具） | dbxio.com / github t8y2/dbx |

## 二、需独立复测的「指标」（非项目真假，标记为营销口径/待核实）

蓝图引用了若干具体数值，本审计**未独立复测**，仅记录为「项目方主张」，不混入代码或能力结论：

| 指标主张 | 出处 | 状态 |
|---|---|---|
| LOCOMO Benchmark 73.70 分 SOTA、Token 消耗降低 96% | SeekDB | ⚠️ 营销口径，未独立跑 LOCOMO 复测 |
| DuckDB TPC-H 比 InnoDB 快 200 倍 | DuckDB 社区 | ⚠️ 营销口径，依赖场景 |
| DBX 11.7k GitHub stars | dbxio.com | ⚠️ 自报，未独立核对 |
| 各项目星标（LocalAI 48k / AgentENV 2.7k / CLIProxyAPI 45k 等） | 白皮书第七章 | ⚠️ 多为 2026-08 时点快照，会漂移 |
| cel-memory-duckdb "2026-07 DuckDB 将 AI 向量检索纳入一等公民" | 白皮书 | ⚠️ DuckDB 早已支持 VSS 扩展，时间点表述需谨慎 |

> 诚实纪律：以上数值若用于对外材料，须标注「待独立复测」；不得作为「已验证性能」陈述。

## 三、按选型铁律的分类处置

AOS 已有记忆基础设施：**Chroma**（向量，`chroma_data/`）、**cognee**（图+知识，`cognee_graph/`）、
**mem0**（记忆层）、`memory/memory.py`（L3 实现）。据此分类：

| 层 | 项目 | 处置 | 理由（铁律） |
|---|---|---|---|
| L1 瞬时 | **DuckDB** | ✅ **接入（可选运行时依赖）** | AOS 缺列式分析引擎；本机已可 import（1.5.4），直接做 mirror_branch 实时统计后端。真实缺口填补。 |
| L2 工作 | **TriviumDB** | 🔗 参考 + opt-in 适配器 | 向量×图谱×文档三位一体契合「粒子私有记忆」；但为 Rust crate，Python 需 `pip install triviumdb`（pyo3 绑定）编译，默认不强制安装，提供惰性适配器。 |
| L2 工作 | **Turso/libSQL** | 🔗 参考 + opt-in 适配器 | 每粒子一库理念极佳；Python 走 `@libsql/client`。同样不强制，提供惰性适配器。 |
| L3 语义 | **KowitoDB** | 🔗 **借鉴，不新增依赖** | AOS 已有 Chroma+cognee 覆盖语义检索；按「现有够好→复用」**不重复造/不新增**。克隆至 vendor 仅作参考审计。 |
| L3 语义 | **txtai** | 🔗 **借鉴，不新增依赖** | 同上，cognee 已覆盖图+RAG。克隆至 vendor 作参考。 |
| L4 传承 | **SeekDB** | 🔗 参考（pip/yum 安装，非 git 克隆） | OceanBase 服务端产品，对本地优先 OS 偏重；代际传承可用「Chroma 快照 + 文件版本归档」轻量实现，不引入重型服务。 |
| 可视化 | **DBX** | 🔗 参考（dev 工具） | 桌面 GUI + MCP Server（`npx @dbx-app/mcp-server`），非 AOS 运行时依赖；克隆至 vendor 作参考，运维期可选启用。 |

### 下载动作（该下载的下载）
已浅克隆 5 个 git 仓库至 `vendor/`（均 MIT/Apache-2.0，参考/审计用，不 import 主链；
与早前 acgs-lite/fractal/nanobot 同口径；`vendor/` 走 `.gitignore` 不入库）：

- `vendor/TriviumDB` ← github.com/YoKONCy/TriviumDB
- `vendor/KowitoDB` ← github.com/kowito/KowitoDB
- `vendor/DBX` ← github.com/t8y2/dbx
- `vendor/libSQL` ← github.com/tursodatabase/libsql （Turso 引擎）
- `vendor/txtai` ← github.com/neuml/txtai

DuckDB / SeekDB 为 pip/yum 安装型产品，**不克隆源码**（DuckDB 为 C++ 巨型仓库，SeekDB 为 OceanBase 服务），
改以 `pip install duckdb` / `pip install seekdb` 文档化安装命令记入本文件与白皮书。

## 四、安装命令速查（按需，非强制）

```bash
# L1 瞬时层（AOS 已实测可用）
pip install duckdb>=1.5

# L2 工作层（opt-in，按项目选其一）
pip install triviumdb          # 向量×图谱×文档
# 或
pip install libsql             # 每粒子一库（libsql 的 Python 绑定）

# L4 传承层（服务端产品，本地优先场景可省略）
pip install seekdb             # 或 yum install seekdb（OceanBase 源）

# 可视化（运维期可选，Node 侧）
npx @dbx-app/mcp-server        # DBX 的 MCP Server，供 AI 编码助手查库
```

## 五、AOS 现有记忆设施的复用映射（避免重复造）

| 记忆阶梯层 | 优先复用 AOS 既有 | 仅在缺口处引入外部 |
|---|---|---|
| L1 瞬时统计 | `evolve/mirror_branch.py` 内存统计 | → DuckDB 做列式复盘（可选增强） |
| L2 工作记忆 | 分形粒子运行时上下文（`fractal/`） | → TriviumDB/Turso 做持久化粒子私有库（opt-in） |
| L3 长期语义 | Chroma + cognee 图 + `memory/memory.py` | → KowitoDB/txtai **不新增**，已覆盖 |
| L4 永久传承 | Chroma 快照 + 文件版本归档 | → SeekDB 仅参考，不强制 |

## 六、诚实分级（本批）

- **② 单元验证**：`src/kernel/store/memory_ladder.py` 四层抽象 + DuckDB L1 后端 + 惰性适配器 + 单测全绿。
- **③ 端到端未做**：未实际灌入真实多模态数据跑通「瞬时→工作→语义→传承」全链路迁移；
  外部库的运行时集成（pip 安装后真连 TriviumDB/Turso/KowitoDB）仅留适配器骨架，未真机验证。
- 外部项目真实性均已 WebSearch 核实，无编撰；具体性能数值标记为待独立复测，未夸大。
