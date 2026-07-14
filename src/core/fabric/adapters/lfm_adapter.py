"""LFM 适配器 —— AOS fabric 的轻量 LLM 供给方（inference.llm 的「低功耗」一极）。

定位（对齐用户「高低搭配」路由诉求）：
- inference.llm 这一能力现在有两类供给方：重的云端/大模型（LiteLLM 网关），
  和**轻量的本地小模型 LFM2（Liquid AI 的开放权重设备端模型，230M~1.2B）**。
- LFM2 真能跑在手机/树莓派（230M 版 213 tok/s、体积 293~375MB），适合简单
  指令/抽取/工具调用类轻任务；复杂推理仍交给大模型——这就是 AOS 的
  「端云合作 / 高低搭配」在 LLM 平面上的体现。

诚实边界（与 STT/TTS 适配器同款）：
- 重依赖（transformers / litellm）全部惰性导入；权重需用户从 HuggingFace 下载
  （LiquidAI/LFM2.5-230M 或 GGUF）。未配置/未下载时 health()=False，路由层
  自动跳过、退回其它 live LLM 供给方，绝不谎报 live。
- 当前沙箱未下载权重 → 默认 not-live（诚实）。用户主机装好权重 + 设
  AOS_LFM_MODEL 后即自动成为 live 的轻量供给方。
"""
from __future__ import annotations

import logging
import os
import threading

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)


class LFMAdapter(BaseAgentAdapter):
    """LFM2 轻量 LLM 供给方（inference.llm）。"""

    def __init__(self, model: str | None = None) -> None:
        # 默认模型：LFM2.5-230M（最小、最快、最适合边缘）；可用 env 覆盖。
        self._model = model or os.environ.get(
            "AOS_LFM_MODEL", "LiquidAI/LFM2.5-230M")
        self._engine = "lfm2"
        self._lock = threading.Lock()
        self._pipe = None  # 懒加载的生成管道
        logger.info("LFMAdapter: model=%s", self._model)

    @property
    def engine_id(self) -> str:
        return "lfm2"

    def advertise_capabilities(self) -> list[Capability]:
        # 与 LiteLLMAdapter 同属 inference.llm —— 路由层据此做高低搭配。
        return [Capability.LLM_GATEWAY]

    # ---- 引擎可用性（如实）----
    def _have_runtime(self) -> bool:
        try:
            import transformers  # noqa: F401
            return True
        except Exception:
            try:
                import litellm  # noqa: F401
                return True
            except Exception:
                return False

    def _weights_ready(self) -> bool:
        # GGUF / 本地路径：文件存在即视为就绪
        if self._model.lower().endswith((".gguf", ".bin", ".safetensors", ".onnx")):
            return os.path.isfile(self._model)
        # HF repo id：仅检查环境变量是否显式要求「强制认为就绪」，否则需联网拉取
        # —— 为诚实起见，不假设已缓存；用户设 AOS_LFM_ASSUME_READY=1 可跳过。
        return os.environ.get("AOS_LFM_ASSUME_READY", "0") == "1"

    def health(self) -> bool:
        return self._have_runtime() and self._weights_ready()

    def health_detail(self) -> dict:
        return {
            "engine": self._engine,
            "model": self._model,
            "live": self.health(),
            "runtime_available": self._have_runtime(),
            "weights_ready": self._weights_ready(),
            "note": "需 transformers/litellm + LFM2 权重（HuggingFace LiquidAI/LFM2.5-*）。"
                    "未就绪时路由层自动退回其它 live LLM 供给方。",
        }

    def _ensure_loaded(self):
        if self._pipe is not None:
            return self._pipe
        try:
            from transformers import pipeline
            self._pipe = pipeline(
                "text-generation",
                model=self._model,
                device_map="auto",
                torch_dtype="auto",
            )
            return self._pipe
        except Exception as e:
            raise RuntimeError(f"LFM2 加载失败: {e}")

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        prompt = (payload.get("prompt") or payload.get("message") or "").strip()
        if not prompt:
            return InvokeResult(ok=False, error="LFM2 需要 prompt")
        if not self.health():
            return InvokeResult(
                ok=False,
                error="LFM2 权重未就绪（需 transformers/litellm + 下载 "
                      f"{self._model}）。已退回其它 live LLM 供给方。",
            )
        try:
            with self._lock:
                pipe = self._ensure_loaded()
                out = pipe(prompt, max_new_tokens=int(payload.get("max_tokens", 128)))
            text = out[0]["generated_text"] if isinstance(out, list) else str(out)
            return InvokeResult(ok=True, data={"text": text, "engine": "lfm2",
                                              "model": self._model})
        except Exception as e:
            return InvokeResult(ok=False, error=f"LFM2 推理失败: {e}")
