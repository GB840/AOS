"""Skill CLI 共享工具：让核心 skill 可脱离 AOS 大脑独立运行。

STATUS: dormant — 未被 __init__.py 导入，未被核心系统引用，
kernel/skills_bridge.py 显式跳过。仅作为独立演示场景的预留工具。
如需激活：在 __init__.py 中添加 import 并注册到 SkillRegistry。

对应战略建议（消化 awesome-llm-apps）：每个核心 skill 都应能 `python -m skills.<name>` 独立跑，
降低准入门槛。本模块只服务于该独立演示场景；AOS 运行时 skill 仍优先走 brain.chat。

关键点：litellm 在缺 provider 时会向 stdout 直接 print "Provider List" 横幅，
会污染 CLI 的 JSON 输出，因此 _standalone_chat 用 redirect_stdout 临时抑制。
"""

import os
import io
import contextlib


def _standalone_chat(prompt: str, model: str | None = None) -> str:
    """Brain-less 回退：直接用 litellm 调模型，证明 skill 脱离 AOS 大脑也能跑。

    返回模型文本；若缺依赖/缺 key/调用失败，返回带前缀的友好字符串（绝不抛异常，
    保证 skill 独立运行时输出始终是合法 JSON 的 value）。
    """
    try:
        import litellm
    except ImportError:
        return "[LLM 不可用] 未安装 litellm：pip install litellm"

    model = model or os.getenv("AOS_EXAMPLE_MODEL", "zhipu/glm-4-flash")

    if model.startswith("zhipu/") and not os.getenv("ZHIPU_API_KEY"):
        return "[LLM 不可用] 需 export ZHIPU_API_KEY=... 或 --model + OPENAI_API_KEY"
    if not model.startswith("zhipu/") and not os.getenv("OPENAI_API_KEY"):
        return "[LLM 不可用] 需 export OPENAI_API_KEY=... 或 ZHIPU_API_KEY"

    try:
        # litellm 缺 provider 时向 stdout 打印 Provider List 横幅，临时抑制以保持 CLI 输出为纯 JSON
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            resp = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
        return resp.choices[0].message.content
    except Exception as e:  # noqa: BLE001
        return f"[LLM 调用失败] {e}"
