"""AOS 可观测 (Langfuse 真实接入) — OBSERVABILITY PLANE.

在 chat/任务请求路径上发出 Langfuse trace (input/output/metadata 含 meta
分层), best-effort flush。未配置密钥时静默禁用 (不阻断主流程)。

复用 fabric 的 LangfuseAdapter (薄封装真实 langfuse.Langfuse), 不在 AOS
内重造遥测 —— 这正是 "集成层只做胶水" 的定位。
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

# langfuse 装在 default venv (sandbox 禁止 pip 在 aos venv 落地),
# 通过 AOS_EXTRA_SITE 低优先级追加其 site-packages。
_EXTRA = os.getenv("AOS_EXTRA_SITE")
if _EXTRA:
    for _p in (_EXTRA, os.path.join(_EXTRA, "win32"), os.path.join(_EXTRA, "pythonwin")):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.append(_p)

from core.fabric.adapter import InvokeRequest
from core.fabric.adapters.observability_langfuse_adapter import LangfuseAdapter

logger = logging.getLogger(__name__)


class LangfuseTracer:
    """在请求路径上发 Langfuse trace 的薄封装。"""

    def __init__(self) -> None:
        self._public = os.getenv("LANGFUSE_PUBLIC_KEY", "")
        self._secret = os.getenv("LANGFUSE_SECRET_KEY", "")
        self._host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self._enabled = bool(self._public and self._secret)
        self._adapter = None
        if self._enabled:
            try:
                self._adapter = LangfuseAdapter(
                    public_key=self._public,
                    secret_key=self._secret,
                    host=self._host,
                )
                logger.info("[langfuse] tracer 已接入 (host=%s)", self._host)
            except Exception as e:  # noqa: BLE001
                logger.warning("[langfuse] 初始化失败, 降级: %s", e)
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._adapter is not None

    def trace(self, name: str, input: Any = None, output: Any = None,
              metadata: Optional[Dict] = None, **kw) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            res = self._adapter.invoke(InvokeRequest(payload={
                "action": "trace",
                "name": name,
                "input": input,
                "output": output,
                "metadata": metadata or {},
            }))
            if res and getattr(res, "ok", False):
                return (res.data or {}).get("trace_id")
        except Exception as e:  # noqa: BLE001
            logger.debug("[langfuse] trace 失败(忽略): %s", e)
        return None


__all__ = ["LangfuseTracer"]
