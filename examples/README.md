# AOS examples/ —— 独立可跑的最小示例

> 设计哲学（消化 awesome-llm-apps 的用户体验）：**3 行启动、端到端闭环、零 AOS 内部依赖**。
> 每个示例都是一个**完整可跑的独立应用**，不 import `brain`、不依赖 DeerFlow / Hermes / OpenClaw / fabric。
> 它们证明：AOS 的能力（对话 / RAG / 代码审查）离开「大脑」也能独立工作。

## 为什么有这个目录

awesome-llm-apps 最大的优点是**零摩擦启动**：

```bash
cd pdf_qa_bot && pip install -r requirements.txt && streamlit run app.py
```

而 AOS 的完整启动要拉起 4 个进程（API :8000 / Web :8501 / OpenClaw :18789 / DeerFlow :2026），
普通开发者 clone 后大概率在前 10 分钟放弃。`examples/` 把 AOS 的**单项能力**抽出来，
让任何人 `pip install -r requirements.txt && python app.py` 就能立刻看到效果。

## 现有示例

| 示例 | 能力 | 依赖 | 启动 |
|---|---|---|---|
| `chat_bot/` | 纯对话 | litellm | `cd chat_bot && pip install -r requirements.txt && python app.py -m "你好"` |
| `pdf_qa/` | 纯 RAG（ChromaDB + LiteLLM） | litellm, chromadb | `cd pdf_qa && pip install -r requirements.txt && python app.py --docs ./docs -q "讲了什么"` |
| `code_review/` | 单 skill 核心逻辑（代码审查） | litellm | `cd code_review && pip install -r requirements.txt && python app.py -f ../src/skills/vimax.py` |

## 配置 LLM

所有示例通过 [litellm](https://docs.litellm.ai) 调用模型，兼容 OpenAI / 智谱 GLM / 硅基流动 等：

```bash
export ZHIPU_API_KEY=...      # 默认模型 zhipu/glm-4-flash
# 或
export OPENAI_API_KEY=...     # 用 --model gpt-4o-mini 等
```

可用 `--model` 覆盖默认模型（任何 litellm 支持的模型名）。
