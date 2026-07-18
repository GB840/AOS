"""AOS 元调度引擎包 — L3.5 顶层 DISPATCH/POLICY/TRUST 决策层。

源码重建说明:原 __init__.py 丢失(仅 .pyc 残留),按调用点契约
(brain.py + main.py + tests + meta_orchestrator.proto) 于 2026-07-19 重建。
"""
from __future__ import annotations

from .engine import MetaOrchestratorEngine, classify_intent

__all__ = ["MetaOrchestratorEngine", "classify_intent"]
