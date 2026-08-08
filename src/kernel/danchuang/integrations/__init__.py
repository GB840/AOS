"""开源库集成模块。

将 LangGraph、CrewAI 等前沿开源框架真正接入单创OS，
替代此前的理念借鉴式自研实现。

──────────────────────────────────────────────────────────────
惰性导入说明（2026-08-08，与 danchuang/llm/__init__.py 同一处理）：

    本模块的两个引擎都依赖重型编排框架（LangGraph / CrewAI）。原先在
    顶层直接 import，任何人只要 `import kernel.danchuang.integrations`
    就必须先装齐这两套框架，否则整个包 ModuleNotFoundError 炸掉。

    这两个框架是【可选增强】而非核心：AOS 自带 Playbook 工作流与
    autopilot 调度，不装照样跑。所以按母纲原则 3/7（一键安装·技术普惠），
    它们已从 pyproject 的必装 dependencies 移入可选组 [orchestration]，
    这里改为 PEP 562 惰性导入，缺依赖时给可照敲的安装命令。
──────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅供类型检查器与 IDE 补全，运行时不执行
    from .crewai_engine import CrewAIOrchestrator
    from .langgraph_engine import LangGraphWorkflowEngine

__all__ = ["LangGraphWorkflowEngine", "CrewAIOrchestrator"]

# 符号 → (子模块, 所需可选依赖组, 具体第三方包)
_LAZY_SYMBOLS = {
    "LangGraphWorkflowEngine": (".langgraph_engine", "orchestration", "langgraph"),
    "CrewAIOrchestrator": (".crewai_engine", "orchestration", "crewai"),
}


def __getattr__(name: str) -> Any:
    """PEP 562：按需加载编排引擎，缺依赖时报可执行的补救命令而非裸崩。"""
    entry = _LAZY_SYMBOLS.get(name)
    if entry is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, extra, pkg = entry
    import importlib

    try:
        module = importlib.import_module(module_name, __name__)
    except ImportError as exc:
        raise ImportError(
            f"{name} 需要可选依赖 {pkg}（依赖组 [{extra}]）。\n"
            f"缺失原因: {exc}\n"
            f"安装命令: pip install -e \".[{extra}]\"\n"
            f"提示：不装也不影响 AOS 核心 Playbook 工作流与 autopilot 自主环。"
        ) from exc

    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)
