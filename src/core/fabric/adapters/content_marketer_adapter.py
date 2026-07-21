"""内容营销智能体（Content Marketer Agent）—— AOS 第一个样板智能体。

输入一个主题，自动完成：
  1. 搜索素材（web.search）
  2. LLM 写视频脚本（inference.llm）
  3. 生成视频（media.video）

设计原则：
- 复用 FabricHub 统一路由，不另造轮子
- 每步都有真实闸门，不谎报成功
- 失败优雅降级：搜不到素材就纯生成，LLM 不可用就用模板
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult, extract_media_url
from core.fabric.capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.environ.get(
    "AOS_CONTENT_OUTPUT_DIR",
    os.path.join("data", "workspaces", "fabric", "content"),
)


def _output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


@dataclass
class ContentResult:
    """一次内容生产的完整结果。"""
    task_id: str
    topic: str
    stages: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    script: str = ""
    video_path: str = ""
    video_duration: float = 0.0
    ok: bool = False
    error: str = ""


class ContentMarketerAdapter(BaseAgentAdapter):
    """内容营销智能体：输入主题 → 搜索 → 写脚本 → 生成视频。

    这是 AOS 第一个样板智能体，演示「用 AOS 的能力组合出新智能体」。
    """

    engine_id = "content-marketer"

    def __init__(self, route_fn=None) -> None:
        self._route_fn = route_fn

    def set_route_fn(self, route_fn) -> None:
        self._route_fn = route_fn

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_MARKETING_VIDEO]

    def health(self) -> bool:
        return self._route_fn is not None

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if self._route_fn is None:
            return InvokeResult(
                ok=False,
                error="content-marketer 未注入 route_fn",
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        topic = (payload.get("topic") or payload.get("task") or payload.get("goal") or "").strip()
        if not topic:
            return InvokeResult(
                ok=False,
                error="缺少 topic（视频主题）",
                engine_id=self.engine_id,
            )
        style = payload.get("style") or "douyin"  # douyin / bilibili / xiaohongshu
        duration = payload.get("duration") or 60  # 目标时长（秒）

        try:
            result = self.produce(topic, style=style, duration=duration)
            return InvokeResult(
                ok=result.ok,
                data={
                    "task_id": result.task_id,
                    "topic": result.topic,
                    "stages": result.stages,
                    "script": result.script,
                    "video_path": result.video_path,
                    "video_duration": result.video_duration,
                    "materials_count": len(result.materials),
                },
                engine_id=self.engine_id,
                error=result.error,
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(
                ok=False,
                error=f"内容生产异常: {e}",
                engine_id=self.engine_id,
            )

    def _route(self, cap: str, payload: Dict[str, Any]) -> Any:
        """调用 route_fn，统一处理返回值。"""
        if self._route_fn is None:
            return None
        try:
            return self._route_fn(cap, payload)
        except Exception as e:
            logger.warning("route %s 失败: %s", cap, e)
            return None

    def _unwrap(self, res: Any) -> Dict[str, Any]:
        """从 InvokeResult 或 dict 中提取 data。"""
        if res is None:
            return {}
        if hasattr(res, "ok") and hasattr(res, "data"):
            if not res.ok:
                return {}
            return res.data or {}
        if isinstance(res, dict):
            return res
        return {}

    def produce(self, topic: str, *, style: str = "douyin", duration: int = 60) -> ContentResult:
        """生产一条营销视频。"""
        task_id = uuid.uuid4().hex[:8]
        result = ContentResult(task_id=task_id, topic=topic)

        # ── 第 1 步：搜索素材 ──
        materials = self._search_materials(topic)
        result.materials = materials
        result.stages.append("search")

        # ── 第 2 步：写脚本 ──
        script = self._write_script(topic, materials, style=style, duration=duration)
        result.script = script
        result.stages.append("script")

        if not script:
            result.error = "脚本生成失败"
            return result

        # ── 第 3 步：生成视频 ──
        video_path, video_dur = self._generate_video(script, task_id, style=style)
        result.video_path = video_path
        result.video_duration = video_dur
        result.stages.append("video")

        if video_path:
            result.ok = True
        else:
            result.error = "视频生成失败"

        return result

    def _search_materials(self, topic: str) -> List[str]:
        """搜索相关素材。失败返回空列表（降级）。"""
        try:
            res = self._route("web.search", {"query": topic, "max_results": 3})
            data = self._unwrap(res)
            items = data.get("results") or data.get("items") or []
            return [
                f"{it.get('title', '')} - {it.get('url', '')}"
                for it in items if it.get("title")
            ][:5]
        except Exception as e:
            logger.warning("搜索素材失败（降级为空）: %s", e)
            return []

    def _write_script(self, topic: str, materials: List[str], *,
                      style: str = "douyin", duration: int = 60) -> str:
        """写视频脚本。优先用 LLM，不可用则用模板。"""
        materials_text = "\n".join(f"- {m}" for m in materials) if materials else "（无参考素材）"

        # 尝试用 LLM 写脚本
        try:
            res = self._route("inference.llm", {
                "prompt": (
                    f"你是一个短视频编剧。请为以下主题写一个约{duration}秒的{style}风格短视频脚本。\n\n"
                    f"主题: {topic}\n\n"
                    f"参考素材:\n{materials_text}\n\n"
                    f"要求:\n"
                    f"1. 分成3-5个分镜，每个分镜一段旁白\n"
                    f"2. 开头要吸引人，结尾要有引导\n"
                    f"3. 语言口语化，符合短视频节奏\n"
                    f"4. 只输出分镜文本，每行一段，不要编号和格式\n"
                ),
            })
            data = self._unwrap(res)
            content = data.get("content") or data.get("output") or data.get("text") or ""
            if content and len(content) > 50:
                return content.strip()
        except Exception as e:
            logger.warning("LLM 写脚本失败（降级模板）: %s", e)

        # 降级：模板脚本
        return self._template_script(topic, style=style, duration=duration)

    @staticmethod
    def _template_script(topic: str, *, style: str, duration: int) -> str:
        """模板脚本生成（LLM 不可用时的兜底）。"""
        lines = [
            f"你知道吗？{topic}正在改变世界。",
            f"很多人还没意识到，{topic}背后的核心逻辑是什么。",
            f"今天我用一分钟给你讲清楚。",
            f"首先，{topic}的本质是效率的提升。",
            f"其次，它会带来全新的可能性。",
            f"关注我，下期讲更多{topic}的干货。",
        ]
        return "\n".join(lines)

    def _generate_video(self, script: str, task_id: str, *, style: str = "douyin") -> tuple:
        """生成视频。返回 (video_path, duration_seconds)。"""
        # 按行拆分成分镜
        scenes = [line.strip() for line in script.split("\n") if line.strip()]
        if not scenes:
            return "", 0.0

        # 根据风格决定尺寸
        size_map = {
            "douyin": "1080x1920",
            "xiaohongshu": "1080x1920",
            "bilibili": "1920x1080",
            "youtube": "1920x1080",
        }
        size = size_map.get(style, "1280x720")

        output_name = f"content_{task_id}"

        try:
            res = self._route("media.video", {
                "text": script,
                "output_name": output_name,
                "size": size,
            })
            data = self._unwrap(res)
            # 统一契约读取：兼容 media-gen(url) / video-maker(output) /
            # comfyui(output_path) 四态分裂，不再因落到非 video-maker 而静默失败。
            addr = extract_media_url(data)
            if addr:
                local = self._localize_video(addr, task_id)
                if local:
                    return local, float(data.get("duration", 0))
        except Exception as e:
            logger.warning("视频生成失败: %s", e)

        return "", 0.0

    def _localize_video(self, addr: str, task_id: str) -> str:
        """把媒体地址落地本地：http(s) 下载到统一 content 目录；本地路径原样返回。

        消除 media-gen 远端临时 url 的 404 风险，并确保 content-marketer 的最终
        交付物是一段本地视频文件（而非可能过期的外链）。
        """
        if addr.startswith(("http://", "https://")):
            import urllib.request
            dest = os.path.join(_output_dir(), f"content_{task_id}.mp4")
            try:
                urllib.request.urlretrieve(addr, dest)
                if os.path.getsize(dest) > 0:
                    return dest
            except Exception as e:  # noqa: BLE001
                logger.warning("下载视频失败: %s", e)
            return ""
        # 本地路径：存在即可用
        if os.path.exists(addr):
            return addr
        return ""
