"""Ollama 本地开源模型直连聊天（开源默认，零外部依赖）。

与 zhipu_chat.py 对称：FabricHub.chat() 的本地优先路径。
- 仅依赖标准库 urllib + 本地 Ollama REST（:11434）。
- 数据不出本机，无 API 分成，兑现「开源默认、闭源 opt-in」。
- 失败返回 None（不抛异常），由调用方降级到云端。

模型选择策略（task_aware）：
- 含"代码/code/编程/function/bug" → qwen2.5-coder:7b
- 含"推理/分析/思考/reason/why/怎么" → deepseek-r1:7b
- 含图/视觉需求（image）→ 跳过本函数（minicpm-v 走多模态路径）
- 默认 → qwen3:8b（通用主力）
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Dict, List, Optional

_LOGGER = logging.getLogger("aos.ollama_chat")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "qwen3:8b")
OLLAMA_CODER_MODEL = os.environ.get("OLLAMA_CODER_MODEL", "qwen2.5-coder:7b")
OLLAMA_REASON_MODEL = os.environ.get("OLLAMA_REASON_MODEL", "deepseek-r1:7b")


def _pick_model(messages: List[Dict[str, str]]) -> str:
    """根据最新用户消息内容挑选最合适的本地模型。"""
    last_user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user = m.get("content", "")
            break
    text = last_user.lower()
    if any(k in text for k in ("代码", "code", "编程", "function", "bug", "实现", "函数", "python", "javascript")):
        return OLLAMA_CODER_MODEL
    if any(k in text for k in ("推理", "分析", "思考", "reason", "why", "怎么", "为什么", "解释")):
        return OLLAMA_REASON_MODEL
    return OLLAMA_DEFAULT_MODEL


def ollama_chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 1024,
    model: Optional[str] = None,
    base_url: str = OLLAMA_BASE_URL,
) -> Optional[str]:
    """用本地 Ollama 生成回复；端点不可达或调用失败返回 None。

    - model=None 时按消息内容自动选模型（coder/reason/default）
    - 仅标准库调用，无 openai 库依赖
    - thinking 模型（qwen3/deepseek-r1/minicpm5）content 为空时回退取 thinking 字段
    """
    try:
        picked = model or _pick_model(messages)
        payload = {
            "model": picked,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "num_predict": max_tokens,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            base_url + "/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.loads(r.read().decode("utf-8"))
        msg = resp.get("message") or {}
        content = msg.get("content", "")
        # thinking 模型可能把答案放进 thinking 字段（content 空）
        if not (isinstance(content, str) and content.strip()):
            thinking = msg.get("thinking", "")
            if isinstance(thinking, str) and thinking.strip():
                content = thinking
        return content.strip() if isinstance(content, str) and content.strip() else None
    except Exception as e:  # noqa: BLE001 - 兜底失败不应阻断主流程
        _LOGGER.warning("Ollama 本地直连失败（将降级到云端）: %s", e)
        return None


def ollama_available(base_url: str = OLLAMA_BASE_URL) -> bool:
    """探测 Ollama 端点是否可达（用于启动时跳过死路径）。"""
    try:
        req = urllib.request.Request(base_url + "/api/tags")
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
        return bool(data.get("models"))
    except Exception:
        return False
