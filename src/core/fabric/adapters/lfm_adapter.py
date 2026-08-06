"""LFM 适配器 —— AOS fabric 的轻量 LLM 供给方（inference.llm 的「低功耗」一极）。

定位（对齐用户「高低搭配」路由诉求）：
- inference.llm 这一能力现在有两类供给方：重的云端/大模型（LiteLLM 网关），
  和**轻量的本地小模型 LFM2（Liquid AI 的开放权重设备端模型，230M~1.2B）**。
- LFM2 真能跑在手机/树莓派（230M 版 213 tok/s、体积 293~375MB），适合简单
  指令/抽取/工具调用类轻任务；复杂推理仍交给大模型——这就是 AOS 的
  「端云合作 / 高低搭配」在 LLM 平面上的体现。

真权重加载（本文件核心升级）：
- 支持两种后端（env AOS_LFM_BACKEND 切换）：
    * transformers（默认）：AutoModelForCausalLM/AutoTokenizer 真加载 HF safetensors；
    * llama_cpp：加载本地 GGUF（llama.cpp，CPU/GPU 通吃，更适合边缘）。
- 权重就绪判定（诚实，绝不谎报 live）：
    * 本地路径（.gguf/.bin/.safetensors/.onnx）：文件存在即就绪；
    * HF repo id：检查本机 HF 缓存目录（~/.cache/huggingface/hub/models--*），
      或显式 AOS_LFM_ASSUME_READY=1（用户确认已下载）；
    * 否则视为未就绪 → health()=False，路由层自动退回其它 live LLM 供给方。
- 沙箱实测 HF 被墙、装不了 LFM2 权重 → 默认 not-live（诚实）。用户主机跑
  tools/fetch-lfm2.ps1 下载到本地后，设 AOS_LFM_MODEL 指向本地路径即自动 live。
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

    # 高低搭配标记：本供给方是「边缘低功耗」一极（路由层可据此优先轻任务）。
    # 修复 P1-1：原为类属性 tier = "edge"，会覆盖基类 BaseAgentAdapter.tier()
    # 方法导致 adapter.tier() 抛 TypeError。改为方法覆盖，行为等价但可调用。
    def tier(self) -> str:
        """覆盖基类 tier() —— LFM2 是边缘低功耗档。"""
        return "edge"

    def __init__(self, model: str | None = None) -> None:
        # 默认模型：LFM2.5-230M（最小、最快、最适合边缘）；可用 env 覆盖。
        self._model = model or os.environ.get(
            "AOS_LFM_MODEL", "LiquidAI/LFM2.5-230M")
        self._engine = "lfm2"
        # 后端选择：显式 AOS_LFM_BACKEND 优先；否则按权重扩展名自动判定
        # （.gguf → llama_cpp；其余 HF repo/safetensors → transformers）。
        env_backend = os.environ.get("AOS_LFM_BACKEND")
        if env_backend:
            self._backend = env_backend.lower()
        elif self._model.lower().endswith(".gguf"):
            self._backend = "llama_cpp"
        else:
            self._backend = "transformers"
        self._lock = threading.Lock()
        self._pipe = None  # 懒加载的生成管道
        logger.info("LFMAdapter: model=%s backend=%s", self._model, self._backend)

    @property
    def engine_id(self) -> str:
        return "lfm2"

    def advertise_capabilities(self) -> list[Capability]:
        # 与 LiteLLMAdapter 同属 inference.llm —— 路由层据此做高低搭配。
        return [Capability.LLM_GATEWAY]

    # ---- 引擎可用性（如实）----
    def _have_runtime(self) -> bool:
        # 用 guarded_import（worker 线程导入）而非主线程裸 import：
        # 避免与 prewarm 后台线程（正向导 litellm 等重依赖）争抢全局 import 锁
        # 导致主线程在 health_report 中无限阻塞（沙箱 litellm 导入极慢时尤甚）。
        from ..resilience import guarded_import

        if self._backend == "llama_cpp":
            return guarded_import("llama_cpp") is not None
        # transformers 后端
        if guarded_import("transformers") is not None:
            return True
        return guarded_import("litellm") is not None

    @staticmethod
    def _hf_cache_dir(repo_id: str) -> str | None:
        """检查本机 HF 缓存是否已有该模型（无需联网）。

        HF 缓存目录命名：~/.cache/huggingface/hub/models--<owner>--<name>
        （repo id 的 '/' 替换为 '--'，并加 'models--' 前缀）。
        """
        import glob
        norm = "models--" + repo_id.replace("/", "--")
        base = os.path.expanduser(os.path.join("~", ".cache", "huggingface", "hub"))
        cand = os.path.join(base, norm)
        if os.path.isdir(cand):
            return cand
        # 兜底：glob 模糊匹配（应对命名微调）
        hits = glob.glob(os.path.join(base, norm + "*"))
        return hits[0] if hits else None

    def _weights_ready(self) -> bool:
        m = self._model
        # 本地权重文件
        if m.lower().endswith((".gguf", ".bin", ".safetensors", ".onnx")):
            return os.path.isfile(m)
        # HF repo id：用户显式确认已就绪
        if os.environ.get("AOS_LFM_ASSUME_READY") == "1":
            return True
        # 否则检查本机 HF 缓存（已下载过即就绪，不假设、不联网）
        return self._hf_cache_dir(m) is not None

    def health(self) -> bool:
        return self._have_runtime() and self._weights_ready()

    def health_detail(self) -> dict:
        return {
            "engine": self._engine,
            "tier": self.tier(),
            "backend": self._backend,
            "model": self._model,
            "live": self.health(),
            "runtime_available": self._have_runtime(),
            "weights_ready": self._weights_ready(),
            "note": "需 transformers/llama_cpp + LFM2 权重（HuggingFace LiquidAI/LFM2.* "
                    "或本地 GGUF）。未就绪时路由层自动退回其它 live LLM 供给方。",
        }

    def _ensure_loaded(self):
        if self._pipe is not None:
            return self._pipe
        try:
            if self._backend == "llama_cpp":
                from llama_cpp import Llama
                self._pipe = Llama(model_path=self._model)
            else:
                from transformers import pipeline
                self._pipe = pipeline(
                    "text-generation",
                    model=self._model,
                    device_map="auto",
                    torch_dtype="auto",
                )
            return self._pipe
        except Exception as e:
            raise RuntimeError(f"LFM2 加载失败 ({self._backend}): {e}")

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        prompt = (payload.get("prompt") or payload.get("message") or "").strip()
        if not prompt:
            return InvokeResult(ok=False, error="LFM2 需要 prompt")
        if not self.health():
            return InvokeResult(
                ok=False,
                error="LFM2 权重未就绪（需 transformers/llama_cpp + 下载 "
                      f"{self._model} 并设 AOS_LFM_MODEL）。已退回其它 live LLM 供给方。",
            )
        try:
            with self._lock:
                pipe = self._ensure_loaded()
                max_tokens = int(payload.get("max_tokens", 128))
                if self._backend == "llama_cpp":
                    out = pipe.create_chat_completion(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=max_tokens,
                    )
                    text = (out.get("choices", [{}])[0]
                            .get("message", {}).get("content", ""))
                else:
                    out = pipe(prompt, max_new_tokens=max_tokens)
                    text = out[0]["generated_text"] if isinstance(out, list) else str(out)
                    # transformers pipeline 默认把输入拼回输出，去掉原 prompt 前缀
                    if isinstance(text, str) and text.startswith(prompt):
                        text = text[len(prompt):].strip()
            return InvokeResult(ok=True, data={"text": text, "engine": "lfm2",
                                              "model": self._model,
                                              "backend": self._backend})
        except Exception as e:
            return InvokeResult(ok=False, error=f"LFM2 推理失败: {e}")
