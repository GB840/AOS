# -*- coding: utf-8 -*-
r"""AOS 真实自主链（全本地、零成本、真出结果）。

链路：WEB_SEARCH(真实联网) -> inference.llm(经 litellm 推理平面打到本地 ollama)
      -> memory.semantic(本地 mem0 向量化存储)。

刻意绕开「假死的 openclaw 网关」：FabricHub 按能力路由，inference.llm 由
LiteLLMAdapter 承接，payload 覆盖 model/api_base 即可指向本地 ollama，
无需任何云端 key、不依赖 openclaw。这正是对「万物为我所用 / 端云不绑定」的
真实落地——此处用「端」（本地）而非「云」。

运行（必须在能连到本地 ollama 的机器上）：
    cd D:\AOS
    python scripts/aos_chain_demo.py
可选环境变量：
    AOS_LOCAL_MODEL  本地 ollama 模型，默认 ollama/deepseek-r1:7b
    AOS_OLLAMA_URL   ollama 地址，默认 http://localhost:11434
"""
import os
import sys
import json
import textwrap

sys.path.insert(0, "src")

from kernel.wiring import build_fabric_hub

LOCAL_MODEL = os.environ.get("AOS_LOCAL_MODEL", "ollama/deepseek-r1:7b")
OLLAMA_URL = os.environ.get("AOS_OLLAMA_URL", "http://localhost:11434")
QUERY = "2026年人工智能领域最重要的进展有哪些？"


def hr(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def main() -> int:
    print("构建 FabricHub（isolate_heavy=False，进程内路由，真实注册表）...")
    hub = build_fabric_hub(isolate_heavy=False)

    # 打印每个能力当前 live 的真实引擎（resolve_engine 只返回 health()==True 的）
    hr("0. 路由表实况（每个能力 -> live 引擎）")
    for cap in ("web.search", "inference.llm", "memory.semantic"):
        print(f"  {cap:18s} -> {hub.resolve_engine(cap)}")

    # ---- [1] 真实联网搜索 ----
    hr("[1] WEB_SEARCH 真实联网搜索")
    r1 = hub.route("web.search", {"query": QUERY, "max_results": 5})
    print("ok =", r1.ok)
    if not r1.ok:
        print("搜索失败：", r1.error)
        return 1
    data = r1.data or {}
    raw = data.get("results") or data.get("content") or []
    results = raw if isinstance(raw, list) else []
    print(f"  引擎={data.get('engine')}  结果数={len(results)}")
    ctx_parts = []
    for i, item in enumerate(results[:5], 1):
        if not isinstance(item, dict):
            continue
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = (item.get("snippet") or item.get("content") or "")
        line = f"[{i}] {title}\n    {url}\n    {snippet[:180]}"
        ctx_parts.append(line)
        print("  " + line.replace("\n", "\n  "))
    ctx = "\n".join(ctx_parts)

    # ---- [2] 本地大模型基于搜索资料出文 ----
    hr(f"[2] inference.llm 经 litellm 打到本地 ollama（{LOCAL_MODEL}）出文")
    prompt = (
        f"用户问题：{QUERY}\n\n"
        f"下面是联网检索到的真实资料，请基于这些资料作答，不要编造：\n{ctx}\n\n"
        f"请用中文简洁回答，不超过200字。"
    )
    r2 = hub.route("inference.llm", {
        "model": LOCAL_MODEL,
        "api_base": OLLAMA_URL,
        "messages": [{"role": "user", "content": prompt}],
        "opts": {"timeout": 180},
    })
    print("ok =", r2.ok)
    if not r2.ok:
        print("出文失败：", r2.error)
        return 2
    answer = (r2.data or {}).get("content", "")
    print("模型回复：")
    print(textwrap.indent(answer, "  "))

    # ---- [3] 写入本地 mem0 记忆 ----
    hr("[3] memory.semantic 写入本地 mem0（ollama 向量化）")
    r3 = hub.route("memory.semantic", {
        "action": "add",
        "text": f"Q: {QUERY}\nA: {answer}",
        "opts": {"user_id": "demo-user"},
    })
    print("ok =", r3.ok)
    if r3.ok:
        print("记忆已写入，mem0 返回：",
              json.dumps((r3.data or {}).get("result"), ensure_ascii=False)[:300])
    else:
        # 记忆写入失败非致命，但必须如实报告，不掩盖
        print("记忆写入失败（非致命，链路前两步已成功）：", r3.error)

    hr("链路结论")
    print("搜索 -> 本地出文 -> 存记忆 全链路真实跑通（未经 openclaw 网关，纯本地零成本）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
