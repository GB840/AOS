# pdf_qa —— 纯 RAG 示例（不依赖 brain/fabric）

端到端 RAG：文档 → ChromaDB 向量索引 → 检索上下文 → LLM 生成回答。
嵌入用 ChromaDB 内置函数（无需 sentence-transformers）；不支持 langchain。

## 3 行启动

```bash
cd examples/pdf_qa
pip install -r requirements.txt
python app.py --docs ./docs --question "资料主要讲了什么？"
```

## 说明

- 支持 `.txt` / `.md`；`.pdf` 需 `pypdf`（已列入 requirements）。
- 首次运行会建立 `.chroma_store/` 索引；再次运行复用。`--reset` 重建。
- 模型配置同 chat_bot：`ZHIPU_API_KEY` 或 `OPENAI_API_KEY` + `--model`。
