"""AOS examples/pdf_qa —— 纯 RAG，不依赖 brain/fabric。

把一组文档（.txt/.md/.pdf）灌进 ChromaDB，用检索到的上下文回答提问。
嵌入用 ChromaDB 内置函数（零额外依赖）；生成用 litellm。

3 行启动：
    cd examples/pdf_qa
    pip install -r requirements.txt
    python app.py --docs ./docs --question "资料主要讲了什么？"
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

try:
    import chromadb
except ImportError:
    sys.exit("缺少 chromadb：请先 `pip install -r requirements.txt`")
try:
    import litellm
except ImportError:
    sys.exit("缺少 litellm：请先 `pip install -r requirements.txt`")


def _load_documents(doc_dir: str):
    """读取目录下文档，返回 [(path, text), ...]。PDF 需 pypdf，缺失则跳过。"""
    out = []
    for path in glob.glob(os.path.join(doc_dir, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        low = path.lower()
        if low.endswith((".txt", ".md")):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                out.append((path, f.read()))
        elif low.endswith(".pdf"):
            try:
                import pypdf

                reader = pypdf.PdfReader(path)
                text = "\n".join((p.extract_text() or "") for p in reader.pages)
                out.append((path, text))
            except Exception:
                print(f"  (跳过 PDF，需 pypdf：{path})")
    return out


def _chunk(text: str, size: int = 800):
    return [text[i : i + size].strip() for i in range(0, len(text), size) if text[i : i + size].strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="AOS 独立 RAG 示例（不依赖 brain/fabric）")
    ap.add_argument("--docs", default="./docs", help="文档目录（.txt/.md/.pdf）")
    ap.add_argument("--question", "-q", default="这份资料主要讲了什么？")
    ap.add_argument("--model", default=os.getenv("AOS_EXAMPLE_MODEL", "zhipu/glm-4-flash"))
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--reset", action="store_true", help="重建索引")
    args = ap.parse_args()

    if args.model.startswith("zhipu/") and not os.getenv("ZHIPU_API_KEY"):
        print("⚠️ 使用 zhipu 模型需 export ZHIPU_API_KEY=...")
        return 2

    client = chromadb.PersistentClient(path="./.chroma_store")
    collection = client.get_or_create_collection("aos_rag_demo")

    if args.reset:
        client.delete_collection("aos_rag_demo")
        collection = client.get_or_create_collection("aos_rag_demo")

    docs = _load_documents(args.docs)
    if not docs:
        print(f"未在 {args.docs} 找到文档。放入 .txt/.md 后再试。")
        return 1

    chunks = [(p, c) for p, text in docs for c in _chunk(text)]
    if collection.count() == 0 or args.reset:
        print(f"索引 {len(chunks)} 个文本块…")
        collection.add(
            ids=[f"c{i}" for i in range(len(chunks))],
            documents=[c for _, c in chunks],
            metadatas=[{"src": p} for p, _ in chunks],
        )
    else:
        print(f"复用已有索引（{collection.count()} 块；--reset 可重建）。")

    results = collection.query(query_texts=[args.question], n_results=args.top_k)
    context = "\n\n".join(results["documents"][0]) if results["documents"] else ""
    prompt = (
        "基于以下资料回答问题，不要编造资料外的内容。\n\n"
        f"资料：\n{context}\n\n问题：{args.question}"
    )

    try:
        resp = litellm.completion(
            model=args.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        print("\n=== 回答 ===\n")
        print(resp.choices[0].message.content)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"生成失败：{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
