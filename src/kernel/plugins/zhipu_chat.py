"""智谱直连兜底聊天。

当 FabricHub 的 inference.llm 路由因外部依赖（openclaw 网关 / litellm /
agnes）未部署或不可达而失败时，用项目内已验证可用的 ZHIPU_API_KEY 直连
open.bigmodel.cn，保证主聊天「开箱即用」。

- 仅依赖 openai 库（项目已有）与 ZHIPU_API_KEY（.env 已配置）。
- 失败返回 None（不抛异常），由调用方决定兜底或诚实报错（理念6/9）。
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Optional

_LOGGER = logging.getLogger("aos.zhipu")

# 智谱 OpenAI 兼容端点（与 kernel/workflow_engine.py 一致）。
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
ZHIPU_DEFAULT_MODEL = "glm-4-flash"


def zhipu_chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 2048,
    api_key: Optional[str] = None,
    model: str = ZHIPU_DEFAULT_MODEL,
    base_url: str = ZHIPU_BASE_URL,
) -> Optional[str]:
    """用智谱直连生成回复；无 key 或调用失败返回 None。"""
    key = api_key or os.environ.get("ZHIPU_API_KEY")
    if not key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model, messages=messages, max_tokens=max_tokens
        )
        content = resp.choices[0].message.content if resp.choices else None
        return content.strip() if isinstance(content, str) else None
    except Exception as e:  # noqa: BLE001 - 兜底失败不应阻断主流程
        _LOGGER.warning("智谱直连兜底失败: %s", e)
        return None
