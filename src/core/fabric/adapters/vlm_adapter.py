"""VLM 视觉语言适配器 —— AOS fabric 的 VISION_UNDERSTAND 平面。

复用 MiniCPM-o 适配器骨架（三级档位 + 惰性依赖 + 诚实 health/invoke），
但面向「图像 / 截图理解」而非全双工语音。

=== 当前主机无 GPU 的现实（用户 2026-07-16 确认）===
- 默认优先云端视觉 API（OpenAI 兼容 /v1/chat/completions，带 image_url）。
- 本地 ollama MiniCPM-V-2 留作未来有 GPU / CPU 慢速兜底，不默认启用。
- 两者皆不可达（无 key / ollama 未起）→ 诚实返回 ok=False，绝不谎报。

铁律对齐（与 stt/tts/omni 适配器一致）：
- 薄：只把 AOS 调用翻译成视觉 API 原生请求，绝不自研视觉模型。
- 诚实：无 key / 服务不可达 → health()=False，invoke 返回真实错误。
- 惰性强依赖：requests 用时才 import，缺失只让对应模式不可用。
- 可测试：真实 HTTP 发送集中在 _describe_cloud / _describe_local，单测可注入
  假 transport 验证 glue（请求体构造、tier 选择、结果投影），无需联网。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading
from typing import Any, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# ---- 端点（环境变量可覆盖，便于用户主机按实际部署改）----
# 云端视觉 API（OpenAI 兼容 chat/completions，支持 image_url）
VLM_CLOUD_BASE = os.environ.get("VLM_CLOUD_BASE", "https://api.openai.com/v1")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "")
VLM_MODEL = os.environ.get("VLM_MODEL", "gpt-4o-mini")  # 可调，默认轻量视觉模型
# 本地 ollama（未来有 GPU / CPU 慢速兜底）
VLM_OLLAMA_URL = os.environ.get("VLM_OLLAMA_URL", "http://localhost:11434")
VLM_OLLAMA_MODEL = os.environ.get("VLM_OLLAMA_MODEL", "minicpm-v:2b")

# ---- 档位（面向「无 GPU」优化：云端优先，本地留作兜底）----
TIER_CLOUD = "cloud"   # 云端视觉 API（无 GPU 即可，需 key）
TIER_LOCAL = "local"   # 本地 ollama MiniCPM-V-2（未来 GPU / CPU 慢）
TIER_AUTO = "auto"
# auto 优先级：当前无 GPU → 先云端（可用即快），本地仅作兜底
_TIER_PRIORITY = (TIER_CLOUD, TIER_LOCAL)


def _pick_tier() -> str:
    """读取档位：优先 VLM_TIER，否则 auto（运行时按可用性自动选）。"""
    return os.environ.get("VLM_TIER") or TIER_AUTO


def _api_key() -> str:
    """动态读取 key：优先环境变量（运行时 .env 重载 / 测试 setenv 都生效），

    回退到模块级常量。模块级常量在 import 时固定，故 health/auth 必须走这里，
    否则 setenv / dotenv 重载后对运行中的适配器不生效。
    """
    return os.environ.get("VLM_API_KEY") or VLM_API_KEY


class VLMAdapter(BaseAgentAdapter):
    """视觉语言适配器（VISION_UNDERSTAND）。薄翻译层，不重造视觉模型。

    支持 cloud / local 两档；默认 auto 自动选可用档，不写死一个。
    """

    def __init__(self, tier: Optional[str] = None) -> None:
        self._tier = tier or _pick_tier()
        self._lock = threading.Lock()
        logger.info("VLMAdapter: tier=%s", self._tier)

    # ---- BaseAgentAdapter 契约 ----
    @property
    def engine_id(self) -> str:
        return "vlm"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.VISION_UNDERSTAND]

    def tier(self) -> str:
        """本引擎在全局三级中的档位＝当前解析后的实际档位（cloud/local）。"""
        return self._resolve_tier()

    # ---- 档位解析 ----
    def _tier_health(self, tier: str) -> bool:
        """某档位是否可用（不连真模型，只做轻量可达性判断）。"""
        if tier == TIER_CLOUD:
            # 有 key 即视为可尝试（真实连通性在 invoke 时验证）
            return bool(_api_key())
        if tier == TIER_LOCAL:
            return self._probe_ollama()
        return False

    def _resolve_tier(self, override: Optional[str] = None) -> Optional[str]:
        """解析最终生效档位。auto → 取第一个可用档；否则用指定档。"""
        tier = override or self._tier
        if tier == TIER_AUTO:
            for t in _TIER_PRIORITY:
                if self._tier_health(t):
                    return t
            return None  # 无可用后端，诚实返回 None
        return tier if self._tier_health(tier) else None

    def available_tiers(self) -> list[str]:
        return [t for t in _TIER_PRIORITY if self._tier_health(t)]

    def health(self) -> bool:
        return self._resolve_tier() is not None

    def health_detail(self) -> dict:
        resolved = self._resolve_tier()
        d = {
            "engine": "vlm",
            "tier": self._tier,
            "resolved_tier": resolved,
            "available_tiers": self.available_tiers(),
            "ready": self.health(),
        }
        if resolved == TIER_CLOUD:
            d.update({
                "mode": "cloud",
                "base": VLM_CLOUD_BASE,
                "model": VLM_MODEL,
                "note": "云端视觉 API（OpenAI 兼容）：无 GPU 即可，需 VLM_API_KEY",
            })
        elif resolved == TIER_LOCAL:
            d.update({
                "mode": "local",
                "ollama_url": VLM_OLLAMA_URL,
                "model": VLM_OLLAMA_MODEL,
                "note": "本地 ollama MiniCPM-V-2：未来有 GPU / CPU 慢速兜底",
            })
        else:
            d.update({
                "note": "无可用 VLM 后端：未配置 VLM_API_KEY 且 ollama 未起",
            })
        return d

    # ---- 执行 ----
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        action = payload.get("action", "describe")
        if action != "describe":
            return InvokeResult(ok=False, error=f"未知 action: {action}（支持 describe）")
        return self._describe(payload)

    def _describe(self, payload: dict) -> InvokeResult:
        """图像理解：image_path 或 image_base64 + prompt -> 文本描述。"""
        # 先确认有可用后端，再处理图像——避免「文件读不到」掩盖「无后端」这一根因
        tier = self._resolve_tier(payload.get("tier"))
        if tier is None:
            return InvokeResult(
                ok=False,
                error="无可用 VLM 后端：未配置 VLM_API_KEY 且本地 ollama 未起/缺视觉模型",
            )

        image_b64 = payload.get("image_base64")
        image_path = payload.get("image_path")
        if not image_b64 and image_path:
            try:
                with open(image_path, "rb") as f:
                    image_b64 = base64.b64encode(f.read()).decode("ascii")
            except Exception as e:  # noqa: BLE001
                return InvokeResult(ok=False, error=f"读取 image_path 失败: {e}")
        if not image_b64:
            return InvokeResult(ok=False, error="需 image_path 或 image_base64")
        prompt = payload.get("prompt") or "请描述这张图片的内容。"

        try:
            if tier == TIER_CLOUD:
                text = self._describe_cloud(image_b64, prompt)
            else:
                text = self._describe_local(image_b64, prompt)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"VLM({tier}) 调用失败: {e}")

        if not text:
            return InvokeResult(ok=False, error=f"VLM({tier}) 返回空结果")
        return InvokeResult(ok=True, data={"text": text, "engine": "vlm",
                                           "tier": tier, "prompt": prompt})

    # ---- 真实传输（可注入，便于单测）----
    def _build_cloud_body(self, image_b64: str, prompt: str) -> dict:
        """构造云端视觉 API 请求体（纯函数，便于单测，不触网）。"""
        return {
            "model": VLM_MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }],
            "stream": False,
        }

    def _describe_cloud(self, image_b64: str, prompt: str) -> str:
        """云端视觉 API：OpenAI 兼容 /v1/chat/completions，带 image_url。"""
        url = VLM_CLOUD_BASE.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {_api_key()}",
            "Content-Type": "application/json",
        }
        body = self._build_cloud_body(image_b64, prompt)
        import requests  # 惰性
        resp = requests.post(url, json=body, headers=headers, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"API {resp.status_code}: {resp.text[:300]}")
        return resp.json()["choices"][0]["message"]["content"]

    def _describe_local(self, image_b64: str, prompt: str) -> str:
        """本地 ollama MiniCPM-V-2：POST /api/chat（带 images 字段）。"""
        import urllib.request
        url = VLM_OLLAMA_URL.rstrip("/") + "/api/chat"
        body = {
            "model": VLM_OLLAMA_MODEL,
            "messages": [{
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }],
            "stream": False,
        }
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data.get("message", {}).get("content", "")

    # ---- 本地探活 ----
    def _probe_ollama(self) -> bool:
        """探活本地 ollama 且确认视觉模型已装（stdlib urllib，零依赖）。

        不只看 ollama 进程活着，还要确认 VLM_OLLAMA_MODEL 在 /api/tags 列表里——
        否则会出现「health=True 但 invoke 因模型缺失失败」的表里不一（沙箱里
        ollama 跑的是 minicpm-mem 而非视觉模型）。
        """
        try:
            import urllib.request
            url = VLM_OLLAMA_URL.rstrip("/") + "/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                if r.status != 200:
                    return False
                data = json.loads(r.read().decode("utf-8"))
            models = {m.get("name", "") for m in data.get("models", [])}
            return VLM_OLLAMA_MODEL in models
        except Exception as e:  # noqa: BLE001
            logger.info("ollama 探活失败: %s", e)
            return False
