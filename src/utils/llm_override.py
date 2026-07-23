"""请求级 LLM 覆盖（BYOK 租户 key 注入推理平面）。

机制：HTTP 层解析租户后，把该租户的 BYOK 默认供应商负载
（model / api_base / api_key / opts）通过 contextvars 挂到当前请求上下文；
LiteLLMAdapter 构造 `litellm.completion()` 调用时读取并合并——从而让
`/api/chat`、`run_task` 总结步、autopilot 规划步等**所有 LLM_GATEWAY 调用**
自动走租户自己填的 key，而无需改动每条调用链。

设计要点（对照 AOS 宪法）：
- 能力即路由（§5）：租户 key 只在该租户请求内生效，跨请求隔离。
- 并发安全：用 contextvars 而非全局变量，随 asyncio.to_thread 上下文传播到
  内核线程；OrchestrationChiplet 的工具执行子线程不调 LLM，故覆盖对其 LLM 步仍有效。
- 零回归：仅当请求 payload 未显式带 api_key 时生效（BYOK 直调 chat 已带 key 则不覆盖）；
  无覆盖时行为与原来完全一致（走 env 配置）。
- 局限（诚实标注）：当前为请求级隐式透传，未做显式 per-request 参数穿链；
  高并发多租户下如需更强隔离，后续升级为显式透传（见 §5 权限即边界）。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Dict, Optional

# payload 形状与 byok.resolve_tenant_payload 一致：
# {"model":..., "api_base":..., "api_key":..., "opts": {"custom_llm_provider":"openai"}}
_LLM_OVERRIDE: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "aos_llm_override", default=None
)


def set_llm_override(payload: Dict[str, Any]) -> None:
    """设置当前请求的 LLM 覆盖负载。"""
    _LLM_OVERRIDE.set(payload)


def get_llm_override() -> Optional[Dict[str, Any]]:
    """读取当前请求的 LLM 覆盖负载（无则 None）。"""
    return _LLM_OVERRIDE.get()


def clear_llm_override() -> None:
    """清除当前请求的 LLM 覆盖负载。"""
    _LLM_OVERRIDE.set(None)


class llm_override:
    """上下文管理器：进入时 set 覆盖，退出时 clear。

    用法::

        with llm_override(payload):
            result = hub.chat(message)   # 内部 LLM 调用自动用租户 key
    """

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def __enter__(self) -> "llm_override":
        set_llm_override(self._payload)
        return self

    def __exit__(self, *exc: Any) -> bool:
        clear_llm_override()
        return False
