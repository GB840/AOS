"""AOS examples/chat_bot —— 纯对话，不依赖 brain/fabric。

3 行启动：
    cd examples/chat_bot
    pip install -r requirements.txt
    python app.py --message "你好"

LLM 后端通过 litellm 配置（兼容 OpenAI / 智谱 GLM / 硅基流动 等）：
    export ZHIPU_API_KEY=...        # 默认模型 zhipu/glm-4-flash
    export OPENAI_API_KEY=...        # 配合 --model gpt-4o-mini
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    import litellm
except ImportError:
    sys.exit("缺少 litellm：请先 `pip install -r requirements.txt`")


def _resolve_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.getenv("ZHIPU_API_KEY"):
        return "zhipu/glm-4-flash"
    if os.getenv("OPENAI_API_KEY"):
        return "gpt-4o-mini"
    return "zhipu/glm-4-flash"


def main() -> int:
    ap = argparse.ArgumentParser(description="AOS 独立对话示例（不依赖 brain/fabric）")
    ap.add_argument("--message", "-m", default="你好，简单介绍一下你自己。", help="发给模型的问题")
    ap.add_argument("--model", default=None, help="模型名（litellm 支持的任何模型）")
    args = ap.parse_args()

    model = _resolve_model(args.model)

    # 选中 provider 必须有对应 key
    if model.startswith("zhipu/") and not os.getenv("ZHIPU_API_KEY"):
        print("⚠️ 使用 zhipu 模型需 export ZHIPU_API_KEY=...")
        return 2
    if not model.startswith("zhipu/") and not os.getenv("OPENAI_API_KEY"):
        print("⚠️ 使用非 zhipu 模型需 export OPENAI_API_KEY=...（或用 ZHIPU_API_KEY + 默认模型）")
        return 2

    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": args.message}],
            temperature=0.7,
        )
        print(resp.choices[0].message.content)
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"调用模型失败：{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
