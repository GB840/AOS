"""AOS 合规基础设施包 — 审计 / 身份 / 追踪。

注意:PII 检测/脱敏的 ComplianceLayer 主实现在 src/kernel/compliance.py(仍工作)。
本包仅提供合规基础设施(audit log / AID identity / call trace),所有模块零外部
依赖,落盘 jsonl/json,与 AOS "诚实/可观测" 铁律一致。

源码重建说明:原 .py 文件曾丢失(仅 __pycache__/*.pyc 残留),无法被 Python 3.13/3.14
加载(brain.py _init_compliance 必然 ImportError)。本目录源码按调用点契约
(brain.py + main.py + web/app.py + tests/) 于 2026-07-19 重建,行为对齐原 API。
"""
from __future__ import annotations

from .audit import AuditEvent, AuditLogger, get_audit_logger
from .identity import AIDGenerator, Identity, get_aid_generator
from .trace import Tracer, get_tracer

__all__ = [
    "AuditEvent",
    "AuditLogger",
    "get_audit_logger",
    "AIDGenerator",
    "Identity",
    "get_aid_generator",
    "Tracer",
    "get_tracer",
]
