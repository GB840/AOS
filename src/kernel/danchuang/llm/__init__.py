"""LLM 提供者模块。

为单创OS提供统一的大语言模型调用接口，支持：
- MockLLM：模拟 LLM，用于无网络/无 key 测试
- LocalLLM：本地模型（预留接口，可接 llama.cpp / transformers / ollama）
- RemoteLLM：远程 API（OpenAI / 阿里云 / DeepSeek 等）

──────────────────────────────────────────────────────────────
惰性导入说明（2026-08-08 实跑发现的「包初始化连坐」）：

    provider.py 本身零第三方依赖（只用 abc/dataclasses/typing 标准库），
    但本文件原先在顶层 `from .langchain_adapter import LangChainLLMAdapter`，
    而 langchain_adapter 依赖 crewai。实测后果：

        >>> import kernel.danchuang.llm.provider
        ModuleNotFoundError: No module named 'crewai'

    —— 用户只想用 MockLLM 跑离线测试，却被一个可选的重编排框架拖死。
    这直接违反母纲原则 3「完整开源·一键安装」与原则 7「技术普惠·8G 旧电脑能跑」。

    改用 PEP 562 模块级 __getattr__ 惰性导入：轻量符号照常即时可用，
    重依赖符号只在真正被访问时才加载；缺依赖时给出可直接照敲的安装命令，
    而不是在 import 阶段就把整个包炸掉。
──────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

# 轻量符号：零第三方依赖，保持即时导入。
from .provider import LLMProvider, LLMResponse, get_default_provider

if TYPE_CHECKING:  # 仅供类型检查器与 IDE 补全，运行时不执行
    from .langchain_adapter import LangChainLLMAdapter

__all__ = ["LLMProvider", "LLMResponse", "get_default_provider", "LangChainLLMAdapter"]

# 重依赖符号 → 所需的可选依赖组
_LAZY_SYMBOLS = {
    "LangChainLLMAdapter": (".langchain_adapter", "orchestration"),
}


def __getattr__(name: str) -> Any:
    """PEP 562：按需加载重依赖符号，缺依赖时报可执行的补救命令而非裸崩。"""
    entry = _LAZY_SYMBOLS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, extra = entry
    import importlib

    try:
        module = importlib.import_module(module_name, __name__)
    except ImportError as exc:
        raise ImportError(
            f"{name} 需要可选依赖组 [{extra}]（LangGraph / CrewAI 等编排框架）。\n"
            f"缺失原因: {exc}\n"
            f"安装命令: pip install -e \".[{extra}]\"\n"
            f"提示：不装也不影响 AOS 核心与 MockLLM/本地模型链路正常使用。"
        ) from exc

    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)
