"""可选重依赖不得连坐核心模块（2026-08-08 实跑发现后新增）。

背景（真实故障，非假设）：
    `kernel/danchuang/llm/provider.py` 只用 abc / dataclasses / typing 标准库，
    零第三方依赖。但父包 `__init__.py` 原先在顶层
    `from .langchain_adapter import LangChainLLMAdapter`，而它依赖 crewai：

        >>> import kernel.danchuang.llm.provider
        ModuleNotFoundError: No module named 'crewai'

    用户只想用 MockLLM 跑离线测试，却被一个可选的重型编排框架整个拖死。
    同样的连坐也发生在 `kernel/danchuang/integrations/__init__.py`（langgraph）。

    更根本的问题是 pyproject 把 langgraph / langchain-core / crewai 列为
    【必装】dependencies —— 而真机实证它们压根没装，api.main 照样起、
    292 条路由照样挂、端到端租户链路照样通。把可选增强钉成必装，
    违反母纲原则 3「完整开源·一键安装」与原则 7「技术普惠·8G 旧电脑能跑」。

修法：
    1. pyproject 把三个包移入可选组 `[orchestration]`
    2. 两个 __init__ 改 PEP 562 惰性导入，缺依赖时抛带安装命令的 ImportError

本测试锁死：轻量符号永不连坐、缺依赖报可执行命令、可选组仍在 pyproject 中声明。
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

# 这些模块无论重依赖装没装，都必须能 import 成功
LIGHTWEIGHT_MODULES = [
    "kernel.danchuang.llm",
    "kernel.danchuang.llm.provider",
    "kernel.danchuang.integrations",
    "kernel.danchuang",
]

# 符号 → 所需的第三方包
HEAVY_SYMBOLS = [
    ("kernel.danchuang.integrations", "LangGraphWorkflowEngine", "langgraph"),
    ("kernel.danchuang.integrations", "CrewAIOrchestrator", "crewai"),
    ("kernel.danchuang.llm", "LangChainLLMAdapter", "crewai"),
]


def _installed(pkg: str) -> bool:
    return importlib.util.find_spec(pkg) is not None


# ──────────────────────────────────────────────────────────────
# 1. 轻量模块不得被重依赖连坐
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module", LIGHTWEIGHT_MODULES)
def test_lightweight_module_imports_without_heavy_deps(module):
    """回归：父包顶层 import 重依赖会让零依赖的子模块也炸掉。"""
    importlib.import_module(module)


def test_core_llm_symbols_are_directly_usable():
    """LLMProvider / get_default_provider 是核心抽象，必须即时可用。"""
    from kernel.danchuang.llm import LLMProvider, LLMResponse, get_default_provider

    assert LLMProvider is not None
    assert LLMResponse is not None
    assert callable(get_default_provider)


# ──────────────────────────────────────────────────────────────
# 2. 缺依赖时的报错必须可执行（不是裸 ModuleNotFoundError）
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("module,symbol,pkg", HEAVY_SYMBOLS)
def test_heavy_symbol_error_carries_install_command(module, symbol, pkg):
    """缺依赖时用户必须一眼看到该敲什么命令，而不是自己猜包名。"""
    mod = importlib.import_module(module)

    if _installed(pkg):
        assert getattr(mod, symbol) is not None
        return

    with pytest.raises(ImportError) as exc:
        getattr(mod, symbol)

    message = str(exc.value)
    assert "orchestration" in message, "错误信息未指明所属可选依赖组"
    assert "pip install" in message, "错误信息未给出可直接照敲的安装命令"


@pytest.mark.parametrize("module", ["kernel.danchuang.integrations", "kernel.danchuang.llm"])
def test_unknown_attribute_raises_attribute_error(module):
    """惰性导入不能把「拼错的属性名」也误报成缺依赖。"""
    mod = importlib.import_module(module)
    with pytest.raises(AttributeError):
        mod.ThisSymbolDoesNotExist


# ──────────────────────────────────────────────────────────────
# 3. pyproject 声明守门：重依赖不得再回到必装列表
# ──────────────────────────────────────────────────────────────

def test_heavy_frameworks_stay_optional_in_pyproject():
    """守门：谁再把 langgraph/crewai 挪回必装 dependencies，这里立刻红灯。"""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    start = text.index("dependencies = [")
    end = text.index("]", start)
    required_block = text[start:end]

    offenders = [p for p in ("langgraph", "langchain-core", "crewai")
                 if f'"{p}' in required_block]
    assert not offenders, (
        f"以下重型框架被放回必装依赖: {offenders}。"
        "它们是可选增强（核心链路实测不需要），必须留在 [orchestration] 组，"
        "否则违反母纲原则 3「一键安装」与原则 7「8G 旧电脑能跑」。"
    )

    assert "orchestration = [" in text, "可选依赖组 [orchestration] 声明丢失"
