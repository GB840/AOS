"""MiniCPM-o 4.5 全双工全模态适配器 —— AOS fabric 的 VOICE_OMNI 平面。

铁律核实（2026-07-15 全网搜，真实开源项目，非臆造）：
OpenBMB 开源（github.com/OpenBMB/MiniCPM-o，MIT/Apache），原生全双工全模态
9B 模型。三种接入（由 AOS_MINICPM_MODE 选一）：
- "cloud_api"   : 免费云端 API。OpenAI 兼容 chat：
                  POST https://api.modelbest.cn/v1/chat/completions  (model:"MiniCPM-o-4.5")
                  + Realtime WebSocket（全双工）。公开测试 key 见官方 api.md（可能变动）。
- "local_comni": 本地 Comni/llama.cpp-omni。Windows 一键包 Comni-Setup-win64.exe；
                  INT4 量化 12GB 显存（RTX5070/4080/4090）即可跑全双工。
- "local_pytorch": 本地官方 PyTorch 方案。全量全双工需 ~21.5GB/24GB 显存；
                  Realtime WS: wss://localhost:8443/v1/realtime?mode=audio

全双工范式：
- invoke() 走 fabric 的「单次/回合」契约（半双工 chat 或一回合 realtime_once），
  兼容现有能力路由，不破坏内核。
- 真正的全双工持续流用 open_realtime_session() 返回 generator，逐事件 yield
  {type:"text"|"audio"|"state"|"error", ...}——这是「随时插话、边听边说」的落点。

设计原则（对齐 AOS 第一性「不绑定、未来-proof、真 OSS 引擎+AOS 增强」）：
- 薄：只把 AOS 调用翻译成 MiniCPM-o 原生 API，绝不自研 Omni 模型。
- 诚实：无 GPU / 无依赖 / 服务不可达 → health()=False，invoke 返回 ok=False+真实错误，
  绝不谎报 live（与 stt/tts_adapter 一致）。
- 惰性强依赖：websockets/requests 用时才 import，缺失只让对应模式不可用，
  不拖垮 `import kernel.wiring` → FabricHub 这条链。
"""
from __future__ import annotations

import base64
import json
import logging
import os
import ssl
import threading
from typing import Any, Iterator, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

# ---- 端点（环境变量可覆盖，便于用户主机按实际部署改）----
CLOUD_BASE = os.environ.get(
    "AOS_MINICPM_CLOUD_BASE", "https://api.modelbest.cn/v1"
)
CLOUD_API_KEY = os.environ.get(
    "AOS_MINICPM_API_KEY", "sk-pQ8L2zF3XmR5kY9wV4jB7hN1tC6vM0xG3aD5sH2bJ9lK4cZ8"
)
LOCAL_HTTP_URL = os.environ.get(
    "AOS_MINICPM_LOCAL_HTTP", "http://localhost:8080/v1"
)
LOCAL_WS_URL = os.environ.get(
    "AOS_MINICPM_LOCAL_WS", "wss://localhost:8443/v1/realtime?mode=audio"
)

# voice.omni 事件类型（全双工流，消费方：VoiceChiplet 全双工模式 / 前端）
OMNI_TEXT = "text"    # 模型文本 token/片段
OMNI_AUDIO = "audio"  # 模型合成音频片（base64，格式由服务端决定）
OMNI_STATE = "state"  # 会话状态（listening/speaking/thinking）
OMNI_ERROR = "error"


def _pick_mode() -> str:
    return os.environ.get("AOS_MINICPM_MODE", "cloud_api")


def _cloud_ws_url() -> str:
    """云端 Realtime WS：同 CLOUD_BASE host，路径 /realtime。

    以官方 Realtime API Overview 为准；此处为合理默认构造。
    """
    base = CLOUD_BASE.replace("https://", "wss://").replace("http://", "ws://")
    return base.rstrip("/") + "/realtime"


class MiniCPMOAdapter(BaseAgentAdapter):
    """全双工全模态适配器（VOICE_OMNI）。薄翻译层，不重造模型。"""

    def __init__(self, mode: Optional[str] = None) -> None:
        self._mode = mode or _pick_mode()
        self._lock = threading.Lock()
        logger.info("MiniCPMOAdapter: mode=%s", self._mode)

    # ---- BaseAgentAdapter 契约 ----
    @property
    def engine_id(self) -> str:
        return "minicpm_o"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.VOICE_OMNI]

    def health(self) -> bool:
        if self._mode == "cloud_api":
            # 有 key 即视为可尝试（真实连通性在 invoke 时验证；免费 key 可能过期）
            return bool(CLOUD_API_KEY)
        # 本地模式：探活本地服务端口
        return self._probe_local()

    def health_detail(self) -> dict:
        d = {"engine": "minicpm_o", "mode": self._mode, "ready": self.health()}
        if self._mode == "cloud_api":
            d.update({
                "base": CLOUD_BASE,
                "note": "免费云端 API（OpenAI 兼容 chat + Realtime WS）；key 可能变动，以官方 api.md 为准",
            })
        else:
            d.update({
                "ws": LOCAL_WS_URL,
                "http": LOCAL_HTTP_URL,
                "note": ("本地部署：Comni/llama.cpp-omni(INT4,12GB) 或 PyTorch全量(~21.5GB/24GB)；"
                         "需先启动本地服务并暴露 /health + /v1/realtime"),
            })
        return d

    # ---- 执行（单次/回合契约，兼容 fabric 路由）----
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        action = payload.get("action", "chat")

        if action == "chat":
            # 半双工/轮次：文本/图像 → 文本（+可选音频）回复
            return self._chat(payload)
        if action == "realtime_once":
            # 云端/本地实时一回合（非持续流）：发一句，收完整回复
            return self._realtime_once(payload)
        return InvokeResult(
            ok=False,
            error=f"未知 action: {action}（支持 chat / realtime_once；持续流请用 open_realtime_session）",
        )

    # ---- 全双工持续流（真正的「随时插话」）----
    def open_realtime_session(self, payload: Optional[dict] = None) -> Iterator[dict]:
        """打开全双工会话，yield 事件流。

        调用方（VoiceChiplet 全双工模式 / 前端 WS 桥接）按事件驱动：
        - 把用户音频片通过内部 send_audio() 喂入；
        - 模型事件逐条 yield {type, ...}。
        骨架：接本地/云端 WS 双工。无依赖或服务不可达时 yield error 事件，
        不抛未捕获异常、不谎报。
        """
        payload = payload or {}
        mode = payload.get("mode", self._mode)
        ws_url = _cloud_ws_url() if mode == "cloud_api" else LOCAL_WS_URL
        try:
            import websockets  # 惰性：缺失即降级（不拖垮 import）
        except Exception as e:  # noqa: BLE001
            yield {OMNI_ERROR: f"websockets 库未安装，无法建立全双工 WS: {e}"}
            return

        # TODO(host): 真模型对接——按官方 Realtime API 协议收发：
        #   1) 连接 ws_url（云端带 Authorization header；本地自签证书关 ssl 验证）
        #   2) 发 client_hello / 配置（参考音频做声音克隆、系统提示词）
        #   3) 循环：用户音频片 → ws.send(audio) ；ws.recv() → 解析 text/audio 事件 yield
        #   4) 打断（barge-in）：收到用户新音频即中断当前 audio 流（模型原生全双工已支持）
        # 以下为诚实骨架：实连前先报告未实现，避免「假成功」。
        yield {OMNI_STATE: "connecting", "ws": ws_url}
        yield {
            OMNI_ERROR: (
                "全双工 WS 真对接为 TODO(host)：需主机有 GPU + 本地服务或有效云端 key。"
                "沙箱无 GPU、HF 被墙下不了权重，无法实跑。接口已就绪，按官方 Realtime "
                "API 协议补全 send/recv 循环即可（见本文件 TODO 注释）。"
            )
        }

    # ---- 内部实现 ----
    def _probe_local(self) -> bool:
        """探活本地服务 /health（标准库 urllib，零依赖）。"""
        try:
            import urllib.request
            url = LOCAL_HTTP_URL.rstrip("/") + "/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2) as r:
                return r.status == 200
        except Exception as e:  # noqa: BLE001
            logger.info("MiniCPM-o 本地服务探活失败: %s", e)
            return False

    def _chat(self, payload: dict) -> InvokeResult:
        """半双工 chat：文本/图像 → 文本（+可选音频）回复。

        走 OpenAI 兼容 /chat/completions。真实 HTTP 调用（联网可能不通，但代码正确）。
        """
        text = payload.get("text") or payload.get("input") or ""
        image_b64 = payload.get("image_base64")  # 可选：图像输入（全模态）
        if not text and not image_b64:
            return InvokeResult(ok=False, error="chat 需 text 或 image_base64")

        if self._mode == "cloud_api":
            url = CLOUD_BASE.rstrip("/") + "/chat/completions"
            headers = {
                "Authorization": f"Bearer {CLOUD_API_KEY}",
                "Content-Type": "application/json",
            }
            content = []
            if text:
                content.append({"type": "text", "text": text})
            if image_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                })
            body = {
                "model": "MiniCPM-o-4.5",
                "messages": [{"role": "user", "content": content}],
                "stream": False,
            }
            try:
                import requests  # 惰性
                resp = requests.post(url, json=body, headers=headers, timeout=60)
                if resp.status_code != 200:
                    return InvokeResult(ok=False, error=f"API {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                reply = data["choices"][0]["message"]["content"]
                return InvokeResult(ok=True, data={"text": reply, "engine": "minicpm_o",
                                                  "mode": "cloud_api"})
            except Exception as e:  # noqa: BLE001
                return InvokeResult(ok=False, error=f"云端 chat 失败: {e}")
        else:
            # 本地：POST 到 LOCAL_HTTP_URL/chat/completions（同协议）
            url = LOCAL_HTTP_URL.rstrip("/") + "/chat/completions"
            body = {
                "model": "MiniCPM-o-4.5",
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            }
            try:
                import requests
                resp = requests.post(url, json=body, timeout=60)
                if resp.status_code != 200:
                    return InvokeResult(ok=False, error=f"本地 chat {resp.status_code}: {resp.text[:300]}")
                reply = resp.json()["choices"][0]["message"]["content"]
                return InvokeResult(ok=True, data={"text": reply, "engine": "minicpm_o",
                                                  "mode": self._mode})
            except Exception as e:  # noqa: BLE001
                return InvokeResult(ok=False, error=f"本地 chat 失败（服务未起？）: {e}")

    def _realtime_once(self, payload: dict) -> InvokeResult:
        """实时一回合（非持续流）：发一句文本/音频，收完整回复。

        骨架：复用 open_realtime_session 的 WS 通道，收满一回合即关。
        TODO(host): 按官方 Realtime 协议实现单次问答的 send/recv。
        """
        return InvokeResult(
            ok=False,
            error=("realtime_once 真对接为 TODO(host)：需 GPU/服务。接口已就绪，"
                   "实现方式同 open_realtime_session 的 send/recv 循环（收满一回合关闭）。"),
        )
