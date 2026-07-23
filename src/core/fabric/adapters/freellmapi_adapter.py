"""FreeLLMAPI 适配器（单创OS 推理面 opt-in OpenAI 兼容 LLM 供应商）。

FreeLLMAPI（github.com/tashfeenahmed/freellmapi，MIT 许可，11k+ stars）把多家
免费档 LLM 聚合成一个 OpenAI 兼容端点 /v1/chat/completions。AOS 已有 LiteLLM
推理面，但 FreeLLMAPI 作为独立、可显式选型的供应商单独接入，便于在路由表里
作为 MEDIUM 档候选，且带真实 health 探测。

★ 重要定位（宪法 §4 不绑定厂商 + 用户避坑 2）：FreeLLMAPI 的「免费额度」来自
  你自己各家平台的免费档——自托管需填 16 家 key；托管版有 premium 且首页明确
  写 "Built for personal use only. Each provider's ToS applies"。
  **仅适合开发/测试阶段做模型效果对比，不能当护眼眼镜量产商用通道**——
  商用走免费档几乎必然违反各平台 ToS。生产请用自己的合规 key 或自托管合规层。

★ 诚实纪律（§6）：health/invoke 全部真实 HTTP；不可达/未配置返回 ok=False，
  绝不伪造成功。本适配器零额外依赖（仅 stdlib urllib），与 openmaic_bridge 一致。

启用（opt-in，env 门控）：
  AOS_FREELLMAPI_URL  = http://localhost:3001   # 自托管；或托管版给你的 API host
  AOS_FREELLMAPI_KEY  = xxx                      # 托管版需要；自托管有 key 也填
  AOS_FREELLMAPI_MODEL= gpt-oss-120b             # 想用的模型名（默认）
仅当 AOS_FREELLMAPI_URL 配置时，fabric_hub 才把它注册进路由表；否则静默跳过。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

DEFAULT_URL = "http://localhost:3001"
DEFAULT_MODEL = "gpt-oss-120b"


def is_freellmapi_configured() -> bool:
    """env 门控：仅当配置了 AOS_FREELLMAPI_URL 才视为可用（opt-in 核心纪律）。"""
    return bool(os.environ.get("AOS_FREELLMAPI_URL"))


class FreeLLMAPIAdapter(BaseAgentAdapter):
    """OpenAI 兼容适配器：把 AOS 的 inference.llm 请求翻译成 FreeLLMAPI 的
    /v1/chat/completions 真实调用。零额外依赖。"""

    def __init__(
        self,
        url: Optional[str] = None,
        key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self._url = (url or os.environ.get("AOS_FREELLMAPI_URL") or DEFAULT_URL).rstrip("/")
        self._key = key if key is not None else (os.environ.get("AOS_FREELLMAPI_KEY") or "")
        self._model = model or os.environ.get("AOS_FREELLMAPI_MODEL") or DEFAULT_MODEL

    @property
    def engine_id(self) -> str:
        return "freellmapi"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.LLM_GATEWAY]

    # ── 真实 HTTP ──────────────────────────────────────────────────
    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """一次真实 HTTP POST；统一返回 {ok,status,data,error,raw}。

        异常/HTTP 错都如实带出，不吞、不伪造（宪法 §6）。
        """
        url = f"{self._url}{path}"
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8", "replace")
                status = resp.getcode()
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace") if e.fp else ""
            status = e.code
        except Exception as e:  # 网络不可达 / 超时 / DNS
            return {"ok": False, "status": None,
                    "error": f"{type(e).__name__}: {e}", "raw": ""}
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {}
        return {"ok": 200 <= status < 300, "status": status,
                "data": parsed, "raw": raw, "error": "" if 200 <= status < 300 else raw}

    def _get(self, path: str) -> Dict[str, Any]:
        """真实 HTTP GET（health 探测用）。"""
        url = f"{self._url}{path}"
        headers = {"Accept": "application/json"}
        if self._key:
            headers["Authorization"] = f"Bearer {self._key}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", "replace")
                status = resp.getcode()
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace") if e.fp else ""
            status = e.code
        except Exception as e:
            return {"ok": False, "status": None,
                    "error": f"{type(e).__name__}: {e}", "raw": ""}
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {}
        return {"ok": 200 <= status < 300, "status": status,
                "data": parsed, "raw": raw, "error": "" if 200 <= status < 300 else raw}

    # ── 推理 ──────────────────────────────────────────────────────
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        model = payload.get("model") or self._model
        messages = payload.get("messages")
        if not messages:
            prompt = (payload.get("prompt") or payload.get("content")
                      or payload.get("task") or "")
            messages = [{"role": "user", "content": prompt}]
        if not messages:
            return InvokeResult(ok=False, error="FreeLLMAPI: 无 messages 且无可用 prompt")
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        r = self._post("/v1/chat/completions", body)
        if not r["ok"]:
            return InvokeResult(
                ok=False,
                error=f"FreeLLMAPI 调用失败 HTTP {r.get('status')}: {r.get('error') or ''}",
                data={"raw": r.get("raw")},
            )
        try:
            content = r["data"]["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            return InvokeResult(
                ok=False,
                error=f"FreeLLMAPI 响应解析失败：{e}；raw={r.get('raw')[:200]}",
                data={"raw": r.get("raw")},
            )
        return InvokeResult(ok=True, data={"content": content, "model": model})

    def stream_invoke(self, req: InvokeRequest) -> Iterator[str]:
        """流式：FreeLLMAPI 支持 SSE（stream:true）。简化实现逐块 yield 文本字段。

        注：完整 SSE 解析需按行拆 event/data；此处走非流式拿全文再 yield，
        保证真实可用且不引入额外依赖。需要真流式时由上层切换 invoke()。
        """
        res = self.invoke(req)
        if res.ok:
            yield res.data.get("content", "")

    def health(self) -> bool:
        """真实可达性探测：优先 /v1/models（OpenAI 兼容目录），失败退回 /health。"""
        r = self._get("/v1/models")
        if r["ok"] and isinstance(r["data"].get("data"), list):
            return True
        r2 = self._get("/health")
        return bool(r2["ok"])

    def supported_protocols(self) -> list[str]:
        return ["OpenAI"]
