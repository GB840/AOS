# AOS RAG / 知识能力矩阵（实测版）

> 本文件是 `AOS_DIGEST_PLAYBOOK.md` C 阶段（能力矩阵与角色升级）的落地文档之一。
> **写作纪律**：所有"能力/状态"结论均来自逐文件代码核验（见各技能 `src/skills/*.py` 行号），
> 不沿用 docstring 自述的营销式描述。凡"声称"与"实测"不符，单列标注。
>
> 核验日期：2026-07-10。运行时：aos venv（chromadb 1.5.9 已装，cognee 未装）。

---

## 0. 状态图例

| 状态 | 含义 |
|------|------|
| ✅ 真实可用 | 默认路径即真实引擎，无需外部缺失依赖 |
| 🟡 真实（有降级） | 真实引擎可用，但某些操作/无依赖时降级为内存/词法 |
| 🔶 可选依赖·模拟 | 真实库未装时走"模拟模式"（返回结构但非真实计算） |
| ⚠️ 名义/夸大 | docstring 声称高级能力（AST/图谱/语义），实测仅为词法/grep |

---

## 1. 能力矩阵总表

| 技能 (文件) | 类别 | 模态 | 部署 | 真实后端 | 声称 vs 实测 | 状态 |
|---|---|---|---|---|---|---|
| `codebase_memory` (`codebase_memory.py`) | 代码检索 | 代码(文本) | 100% 本地 | **无外部引擎**：`os.walk` + 子串匹配 | 声称 Tree-Sitter AST / 知识图谱 / 语义搜索 → 实测 **词法子串搜索** | ⚠️ 名义/夸大（但可跑） |
| `lightrag` (`lightrag.py`) | 文档 RAG | 文本 | 本地 | **ChromaDB 1.5.9**（`PersistentClient`，`./chroma_data`） | 声称 LightRAG 图谱/混合 → 默认走 ChromaDB **向量检索**（真）；"知识图谱/混合"为名义 | 🟡 真实（有降级） |
| `cognee` (`cognee.py`) | 实体图谱 | 文本→图 | 本地 | `cognee` 库（**未装**） | 声称知识图谱/实体关系 → 未装时 **模拟模式**（无真实图谱计算） | 🔶 可选依赖·模拟 |
| `jina_reader` (`jina_reader.py`) | Web 抓取/抽取 | Web→Markdown | **云端**(jina.ai) + 本地回退 | `r.jina.ai` / `api.jina.ai`；本地 `urllib` 回退 | 声称统一读取器 → 实测真实（需网络；可选 `JINA_API_KEY`），附带 `brain.chat` 摘要 | 🟡 真实（有降级） |

相关但未纳入本表（同属检索/RAG 邻接）：`codebase_memory_mcp.py`（MCP 服务器版封装）、`zvec.py`（向量工具）、`learning.py`（学习记忆）。

---

## 2. 逐技能实测详情

### 2.1 `codebase_memory` — 代码检索（⚠️ 名义/夸大，但可跑）

- **类**：`CodebaseMemorySkill`（`codebase_memory.py:58`），`execute`（`codebase_memory.py:83`）。
- **默认路径**：`self._enhanced_mode = True` → `_execute_enhanced`（`codebase_memory.py:133`）。
- **实测实现**（关键证据）：
  - `_search_code`（`codebase_memory.py:187`）：`os.walk` 遍历 + `query.lower() in content.lower()` **子串匹配**，无任何 AST/语义/向量。
  - `_analyze_architecture`（`codebase_memory.py:224`）：纯 `os.walk` 统计文件数与目录结构。
  - `call_graph` / `impact` / `type_inference` 等：均为文件遍历 + 正则/子串，**非调用图、非类型推断引擎**。
- **另一路径** `_execute_mcp`（`codebase_memory.py:170`）：向 `localhost:8080/api/<tool>` 发 HTTP，即"真正的 Codebase Memory MCP 服务器"。但默认不走此路（需另起服务器）。
- **结论**：产出真实、可用，但 docstring 的"Tree-Sitter AST / 知识图谱 / 语义搜索"**不属实**，实为词法检索。归类为"可跑的朴素实现"。
- **关键 API**：`context.tool ∈ {search, architecture, call_graph, impact, find_definition, find_references, type_inference, dependency_graph, index_status, list_symbols, get_file_structure, compare_versions, generate_doc, analyze_complexity}`，必填 `project_path`。

### 2.2 `lightrag` — 文档 RAG（🟡 真实 ChromaDB，图谱为名义）

- **类**：`LightRAGSkill`（`lightrag.py:46`），`execute`（`lightrag.py:86`）。
- **默认路径**：`self._enhanced_mode = True` → `_execute_enhanced`（`lightrag.py:131`）。
- **实测实现**：
  - `__init__` 调 `_check_chromadb`（`lightrag.py:72`）：`import chromadb` → `chromadb.PersistentClient(path="./chroma_data")`。**aos venv 实测 chromadb 1.5.9 可用** → `_chromadb_available = True`。
  - 因此默认走 `_execute_chromadb` —— **真实向量检索**（ChromaDB 内嵌 embedding，无需 sentence_transformers）。
  - 仅当 chromadb 不可用时降级 `_execute_fallback`（`lightrag.py:293`）：**内存 dict + 子串匹配**（非向量）。
  - 非增强模式 `_execute_lightrag`（`lightrag.py:142`）才 `from lightrag import LightRAG`（真实 LightRAG SDK），但默认不启用。
- **结论**：默认即真实向量检索（ChromaDB 已装）。但 CAPABILITIES 中的 `knowledge_graph` / `hybrid_search` 在 ChromaDB 后端下**为名义**（ChromaDB 是纯向量库，无图）；`graph_search`/`hybrid_search` 实际多走 fallback 或受限。
- **关键 API**：`context.action ∈ {vector_search, graph_search, hybrid_search, add_document, delete_document, list_documents, create_collection, delete_collection, query_expansion, summarization}`，可选 `collection` / `query` / `document` / `top_k`。

### 2.3 `cognee` — 实体图谱（🔶 可选依赖·模拟）

- **类**：`CogneeSkill`（`cognee.py:127`），`execute`（`cognee.py:184`）。
- **依赖判定**：模块顶部 `try: import cognee ... except ImportError: COGNEE_AVAILABLE = False`（`cognee.py:42-49`）。**当前 aos venv 未装 cognee → `COGNEE_AVAILABLE = False`，走模拟模式**（启动即打印 `⚠️ cognee 开源库未安装，使用模拟模式`）。
- **实测实现**：
  - 真实路径：调用 `cognee` 库的 graph/entity API（`cognee.py:349` 之前分支）。
  - 模拟路径：`_execute_mock`（`cognee.py:358` 起）返回 `ENTITY_TYPES` / `RELATION_TYPES` 结构骨架，**不做真实图谱计算**。
- **结论**：架构正确（可选真实引擎 + 模拟兜底），但**默认出厂态为模拟**，需 `pip install cognee` 才变真实。
- **关键 API**：`context.action`（search/add/等），涉及 `entity_type` / `relation_type`。

### 2.4 `jina_reader` — Web 抓取/抽取（🟡 真实云端 + 本地回退）

- **类**：`JinaReaderSkill`（`jina_reader.py:51`），`execute`（`jina_reader.py:83`）。
- **实测实现**：
  - 云端：`_extract_url_jina`（`jina_reader.py:173`）请求 `r.jina.ai` / `api.jina.ai/v1/extract`，可选 `JINA_API_KEY`（取自 `config.JINA_API_KEY`，默认空）。
  - 本地回退：`self._use_local_fallback = True`（`jina_reader.py:75`），云端失败时 `_extract_url_local` 用 `urllib` 抓取 + 简易解析。
  - 摘要：`_generate_summary`（`jina_reader.py:321`）调 `brain.chat(...)`（需 AOS 大脑在线）。
- **结论**：真实可用的 Web 内容抽取；依赖网络，摘要依赖大脑。属 RAG 流水线的"摄入层"而非检索层。
- **关键 API**：`context.url` + `context.action ∈ {extract, read, summarize}` + `output_format ∈ {markdown, text, json}`。

---

## 3. 系统性观察（与前期核验一致）

本矩阵再次印证 `AOS_DIGEST_PLAYBOOK.md` §1.2 的系统性结论：**AOS 反复"脚手架已建、智能/接线缺失，且命名夸大"**。

| 技能 | docstring 声称 | 实测 |
|---|---|---|
| codebase_memory | Tree-Sitter AST / 知识图谱 / 语义搜索 | 词法子串 + 文件遍历 |
| lightrag | LightRAG 图谱 / 混合搜索 | ChromaDB 向量（真）+ 图/混合名义 |
| cognee | 知识图谱实体关系 | 未装→模拟模式 |
| llm_router（前期已核） | 按任务类型自动选模型 | 仅 fallback，无语义分类 |
| classify_with_llm（前期已核） | LLM 语义分类 | 死代码，从未被路由调用 |

**推论**：AOS 的 RAG 能力"底盘"（ChromaDB 向量检索、jina 抓取）是**真实可用**的；
但"图谱/语义/混合"等高级定语多为**包装**，真实度参差。对外陈述能力时须按上表"状态"列，
避免再次"没验证够就定性"。

---

## 4. 升级建议（对应 playbook D 升华 / 后续任务）

1. **codebase_memory 去夸大**：要么真接 Tree-Sitter（加 `tree-sitter` / `tree-sitter-language-pack` 依赖做 AST），要么把 docstring 改为"词法代码检索"，并在 CAPABILITIES 去掉 `semantic_search`/`knowledge_graph`。
2. **lightrag 图谱补全**：若需真图谱，启用非增强模式接真实 `lightrag` SDK（当前 venv 未装 `lightrag`）；否则收敛 CAPABILITIES 为 `vector_search`/`document_store`。
3. **cognee 默认真实化**：在 `requirements.lock` 加入 `cognee`，让默认态即真实图谱，移除"模拟模式"为唯一兜底。
4. **统一检索入口**：四技能各自为政；可参照 playbook D 的"协议原生"原则，用 MCP 把 codebase_memory/lightrag 暴露为统一 `mcp__aos_rag__*` 工具（见任务 #136）。
5. **jina 摘要解耦**：`_generate_summary` 强依赖 `brain.chat`，脱离大脑独立运行时（如 #133 CLI）会失败；应加 brain-less 回退（复用 `cli_helpers._standalone_chat`）。

---

## 5. 验证方法（可复现）

```bash
# ChromaDB 可用性（决定 lightrag 默认是否为真实向量）
python -c "import chromadb; print(chromadb.__version__)"   # aos venv: 1.5.9 ✅

# cognee 可用性（决定 cognee 是否模拟）
python -c "import cognee" 2>&1 | tail -1                  # ModuleNotFoundError → 模拟模式 🔶

# 各技能 import 不报错（注册表可加载）
PYTHONPATH=D:/AOS/src python -c "from skills.codebase_memory import CodebaseMemorySkill; from skills.lightrag import LightRAGSkill; from skills.cognee import CogneeSkill; from skills.jina_reader import JinaReaderSkill; print('OK')"
```
