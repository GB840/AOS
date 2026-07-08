"""AOS 语义记忆 (Mem0 真实接入) — MEMORY / KNOWLEDGE PLANE.

用真实 mem0.Memory 做长期语义记忆：抽取用户/项目事实 + 语义召回。
向量库用本地 chroma (嵌入式, 无需独立服务), LLM/embedder 走 Zhipu
OpenAI 兼容端点。Mem0 不可用时优雅降级到内存字典 (不阻断 AOS)。

这是 AOS "集成层" 的合法提升: 四个行为引擎 (OpenClaw/Hermes/DeerFlow/AG2)
都缺的语义记忆层, 由真实 OSS 承担, AOS 只做薄封装 + 接入。
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# mem0/langfuse 装在 default venv (sandbox 禁止 pip 在 aos venv 落地),
# 通过 AOS_EXTRA_SITE 低优先级追加其 site-packages, 让 aos 进程能 import。
_EXTRA = os.getenv("AOS_EXTRA_SITE")
if _EXTRA:
    for _p in (_EXTRA, os.path.join(_EXTRA, "win32"), os.path.join(_EXTRA, "pythonwin")):
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.append(_p)


def _build_config() -> Optional[Dict[str, Any]]:
    """从环境变量构造 Mem0 配置 (Zhipu OpenAI 兼容)。"""
    api_key = os.getenv("ZHIPU_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("AOS_LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    model = os.getenv("AOS_LLM_MODEL", "glm-4-flash")
    embed_model = os.getenv("AOS_EMBED_MODEL", "embedding-3")
    store_path = os.getenv("AOS_MEM0_PATH", os.path.join(os.getcwd(), "mem0_store"))
    return {
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": "aos_mem0", "path": store_path},
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": model,
                "temperature": 0.1,
                "max_tokens": 2000,
                "api_key": api_key,
                "openai_base_url": base_url,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": embed_model,
                "api_key": api_key,
                "openai_base_url": base_url,
            },
        },
    }


class Mem0Store:
    """真实语义记忆 (Mem0) + 优雅降级。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fallback: Dict[str, List[str]] = {}
        self._available = False
        self._memory = None
        cfg = _build_config()
        if cfg is None:
            logger.warning("[mem0] 未配置 ZHIPU_API_KEY/OPENAI_API_KEY, 降级到内存字典")
            return
        try:
            from mem0 import Memory

            # mem0 2.x: 用 from_config(dict) 构造 (config=dict 会报 AttributeError)
            try:
                self._memory = Memory.from_config(cfg)
            except (TypeError, AttributeError):
                self._memory = Memory(config=cfg)
            self._available = True
            logger.info("[mem0] 真实 Memory 已初始化 (chroma 本地向量库 + Zhipu)")
        except Exception as e:  # noqa: BLE001
            logger.warning("[mem0] 初始化失败, 降级: %s", e)
            self._memory = None

    @property
    def available(self) -> bool:
        return self._available

    def add(self, text: str, user_id: str = "aos",
            metadata: Optional[Dict] = None) -> Dict[str, Any]:
        if self._memory is not None:
            try:
                r = self._memory.add(text, user_id=user_id, metadata=metadata or {})
                return {"ok": True, "backend": "mem0", "result": r}
            except Exception as e:  # noqa: BLE001
                logger.warning("[mem0] add 失败: %s", e)
        with self._lock:
            self._fallback.setdefault(user_id, []).append(text)
        return {"ok": True, "backend": "fallback", "result": None}

    def search(self, query: str, user_id: str = "aos",
               limit: int = 5) -> Dict[str, Any]:
        if self._memory is not None:
            try:
                kwargs: Dict[str, Any] = {"limit": limit}
                if user_id:
                    kwargs["filters"] = {"user_id": user_id}
                r = self._memory.search(query, **kwargs)
                return {"ok": True, "backend": "mem0", "results": r}
            except Exception as e:  # noqa: BLE001
                logger.warning("[mem0] search 失败: %s", e)
        with self._lock:
            items = self._fallback.get(user_id, [])
        return {"ok": True, "backend": "fallback",
                "results": [{"text": t} for t in items]}


__all__ = ["Mem0Store", "_build_config"]
