"""本地 Ollama LLM / VLM 工具函数。

提供统一的本地模型调用接口，给 content flywheel 各模块用。
零成本、离线可用、优雅降级。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认模型
DEFAULT_LLM_MODEL = "qwen2.5-coder:7b"
DEFAULT_VLM_MODEL = "minicpm-v:latest"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"

# 缓存
_model_available: Dict[str, Optional[bool]] = {}


def _check_model(model: str, timeout: float = 5.0) -> bool:
    """检查模型是否可用（带缓存）。"""
    if model in _model_available:
        return _model_available[model] is True

    try:
        import urllib.request
        req = urllib.request.Request(
            f"{DEFAULT_OLLAMA_URL}/api/show",
            data=json.dumps({"name": model}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = resp.status == 200
            _model_available[model] = ok
            return ok
    except Exception as e:
        logger.debug("检查模型 %s 失败: %s", model, e)
        _model_available[model] = False
        return False


def llm_available() -> bool:
    """本地 LLM 是否可用。"""
    return _check_model(DEFAULT_LLM_MODEL)


def vlm_available() -> bool:
    """本地 VLM 是否可用。"""
    return _check_model(DEFAULT_VLM_MODEL)


def llm_chat(prompt: str, *, system: str = "", model: str = None,
             temperature: float = 0.7, max_tokens: int = 2000,
             timeout: float = 120.0) -> str:
    """调用本地 Ollama LLM。

    返回生成的文本，失败返回空字符串。
    """
    model = model or DEFAULT_LLM_MODEL
    if not _check_model(model):
        logger.debug("LLM 模型 %s 不可用", model)
        return ""

    try:
        import urllib.request
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if max_tokens:
            payload["options"] = {"num_predict": max_tokens}

        req = urllib.request.Request(
            f"{DEFAULT_OLLAMA_URL}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.warning("LLM 调用失败: %s", e)
        return ""


def vlm_describe_image(image_path: str, prompt: str = "描述这张图片的内容",
                       model: str = None, timeout: float = 60.0) -> str:
    """用本地 VLM 描述图片内容。

    返回图片描述文本，失败返回空字符串。
    """
    model = model or DEFAULT_VLM_MODEL
    if not _check_model(model):
        logger.debug("VLM 模型 %s 不可用", model)
        return ""

    try:
        import base64
        import urllib.request

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        payload = {
            "model": model,
            "prompt": prompt,
            "images": [img_b64],
            "stream": False,
        }

        req = urllib.request.Request(
            f"{DEFAULT_OLLAMA_URL}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
    except Exception as e:
        logger.warning("VLM 调用失败: %s", e)
        return ""


def list_models() -> List[Dict[str, Any]]:
    """列出本地所有 Ollama 模型。"""
    try:
        import urllib.request
        req = urllib.request.Request(f"{DEFAULT_OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("models", [])
    except Exception as e:
        logger.debug("列出模型失败: %s", e)
        return []
