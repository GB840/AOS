"""ComfyUI 的 FabricHub 适配器 —— 把「节点式视觉生产引擎」作为可路由芯粒接进
AOS 能力路由枢纽。

此前 ComfyUI 只是 legacy brain 栈里的一个 Skill（src/skills/comfyui.py），
FabricHub 新栈里 ``media.image`` / ``media.video`` 路由给本地 ComfyUI（HIGH 优先）与国产 media-gen（MEDIUM 兜底），不再默认走云端 agnes，
本地那台已经跑起来的 ComfyUI 根本没被新栈看见、也没法被一句话自动调起。

本适配器让：
  - ``hub.route("media.image", {prompt: "一只在雨中的猫"})`` 一句话即可出图，
    无需用户指定 action —— 适配器按 payload 自动推断（有图→图生视频/风格迁移，
    无图→文生图），这就是「自觉指挥」的雏形；
  - ComfyUI 是本地服务、零成本、最强隐私，档位 high —— 比云端 agnes 更贴
    AOS「本地优先 / 万物为我所用」；route 级联时云端用不了就回本地 ComfyUI；
  - health() 真实探 /system_info，没起服务就如实 False（不谎报 live）；
  - 修过的真跑坑（seed 非负、ckpt 可配）在此生效，连上就能真出图。

复用而非重写：适配器只是一个薄壳，真正干活的是已通电的 ComfyUISkill。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from typing import Any, Optional

import requests

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability, ENGINE_TIER, TIER_HIGH

logger = logging.getLogger(__name__)


def _infer_action(payload: dict) -> str:
    """一句话→动作 的自觉推断（用户无需指定 action）。

    优先级：视频路径→vid2vid；图片+参考/风格→风格迁移；仅图片→图生视频；
    其它（纯文本 prompt）→文生图（最常用）。
    """
    if payload.get("video_path"):
        return "vid2vid"
    if payload.get("image_path"):
        if payload.get("reference_image") or payload.get("style_prompt"):
            return "style_transfer"
        return "img2vid"
    return "txt2img"


class ComfyUIAdapter(BaseAgentAdapter):
    """FabricHub 引擎：一句话 → ComfyUI 视觉生产（文生图/图生视频/风格迁移…）。"""

    @property
    def engine_id(self) -> str:
        return "comfyui"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.MEDIA_IMAGE, Capability.MEDIA_VIDEO]

    def tier(self) -> str:
        # 本地服务、零成本、最强隐私 —— high 档，比云端 agnes 优先。
        return ENGINE_TIER.get(self.engine_id, TIER_HIGH)

    def health(self) -> bool:
        # ComfyUI 是外部服务，没起就是没起 —— 如实反映，不谎报 live。
        try:
            from utils.config import config
            url = (
                os.environ.get("COMFYUI_BASE_URL")
                or getattr(config, "COMFYUI_BASE_URL", "http://localhost:8188")
            )
            resp = requests.get(f"{url}/system_info", timeout=3)
            return resp.status_code == 200
        except Exception as e:  # noqa: BLE001
            logger.debug("comfyui health check failed: %s", e)
            return False

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        try:
            from skills.comfyui import ComfyUISkill, ComfyUIDirector

            # 自觉指挥：用户没给 action 就按 payload 推断（一句话出图）。
            action = payload.get("action") or _infer_action(payload)
            context = dict(payload)
            context["action"] = action

            # 一句话自觉编排：prompt 含 lora:/controlnet: 语法，或显式传了
            # loras/controlnets/motion/style/model → 先抽结构化意图，交给
            # ComfyUI 动态改节点图（插入 LoRA/ControlNet 并重连），而非模板填参。
            if "intent" not in context:
                has_adv = any(k in payload for k in
                              ("loras", "controlnets", "motion", "style", "model"))
                has_inline = re.search(r"lora:|controlnet:", payload.get("prompt", ""))
                if has_adv or has_inline:
                    director = ComfyUIDirector()
                    intent = director.plan_intent(
                        payload.get("prompt", ""),
                        **{k: payload[k] for k in (
                            "loras", "controlnets", "motion", "style", "model",
                            "image_path", "has_image", "video_path",
                            "reference_image", "style_prompt",
                        ) if k in payload})
                    context["intent"] = intent.to_dict()

            skill = ComfyUISkill()
            out = skill.execute(context)

            ok = bool(out.get("success", False))
            result = out.get("result") or {}
            # 资产落地：ComfyUI 输出在它私有目录（相对 cwd 且有歧义），
            # 拷贝到 AOS 拥有的 out/comfyui/，让网页/下游能稳定引用。
            output_path = self._localize_asset(result.get("output_path"))
            # 调用方直接拿 output_path，无需扒两层嵌套。
            data = {
                "action": action,
                "action_name": out.get("action_name"),
                "output_path": output_path,
                "url": output_path,
                "mode": out.get("mode"),
                "comfyui_available": out.get("comfyui_available"),
                "detail": result,
            }
            return InvokeResult(
                ok=ok,
                data=data,
                error=out.get("error"),
                engine_id=self.engine_id,
            )
        except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
            return InvokeResult(
                ok=False,
                error=f"comfyui invoke failed: {type(e).__name__}: {e}",
                engine_id=self.engine_id,
            )

    @staticmethod
    def _localize_asset(src_path: Optional[str]) -> Optional[str]:
        """把 ComfyUI 私有目录的输出落地到 AOS 拥有的 out/comfyui/。

        返回 AOS 目录下的绝对路径（网页/下游可稳定引用）；src 不存在或拷贝
        失败时退回原始路径的 abspath，不静默丢资产。I/O 全程隔离（芯粒崩溃
        不传染），不阻塞主流程。
        """
        if not src_path:
            return src_path
        src = os.path.abspath(src_path)
        if not os.path.exists(src):
            return src
        try:
            dest_dir = os.path.join("out", "comfyui")
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.abspath(os.path.join(dest_dir, os.path.basename(src)))
            if dest != src:
                shutil.copy2(src, dest)
            return dest
        except Exception as e:  # noqa: BLE001
            logger.warning("comfyui 资产落地失败，退回原始路径: %s", e)
            return src


__all__ = ["ComfyUIAdapter"]
