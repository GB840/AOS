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


@dataclass
class PromoteResult:
    """promote_pipeline 多阶段可干预流水线的完整产出（借鉴 waoowaoo [A][D]）。"""
    goal: str
    stages_done: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    stopped_at: str = ""        # 被 §0.7 闸门挡停的阶段（空串=全程通过）
    ok: bool = False


class ContentMarketerAdapter(BaseAgentAdapter):
    """内容营销智能体：输入主题 → 搜索 → 写脚本 → 生成视频。

    这是 AOS 第一个样板智能体，演示「用 AOS 的能力组合出新智能体」。
    """

    @property
    def engine_id(self) -> str:
        return "content-marketer"

    def __init__(self, route_fn=None) -> None:
        self._route_fn = route_fn

    def set_route_fn(self, route_fn) -> None:
        self._route_fn = route_fn

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_MARKETING_VIDEO, Capability.CONTENT_SHORT_DRAMA]

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
        identity_anchors = payload.get("identity_anchors")  # 跨镜头角色/场景一致性约束（可空）
        short_drama = bool(payload.get("short_drama"))     # 短剧/漫剧模式

        # 走多阶段可干预流水线（借鉴 waoowaoo 分阶段管线 + §0.7 白盒审核）
        if payload.get("pipeline"):
            return self._run_pipeline(
                topic, style=style, duration=duration,
                short_drama=short_drama, identity_anchors=identity_anchors,
            )

        try:
            result = self.produce(
                topic, style=style, duration=duration,
                short_drama=short_drama, identity_anchors=identity_anchors,
            )
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

    def produce(self, topic: str, *, style: str = "douyin", duration: int = 60,
                short_drama: bool = False,
                identity_anchors: Optional[dict] = None) -> ContentResult:
        """生产一条营销视频。"""
        task_id = uuid.uuid4().hex[:8]
        result = ContentResult(task_id=task_id, topic=topic)
        if short_drama:
            result.stages.append("short_drama")  # 标记短剧模式（借鉴 waoowaoo 子能力）

        # ── 第 1 步：搜索素材 ──
        materials = self._search_materials(topic)
        result.materials = materials
        result.stages.append("search")

        # ── 第 2 步：写脚本 ──
        script = self._write_script(
            topic, materials, style=style, duration=duration,
            short_drama=short_drama, identity_anchors=identity_anchors,
        )
        result.script = script
        result.stages.append("script")

        if not script:
            result.error = "脚本生成失败"
            return result

        # ── 第 3 步：生成视频 ──
        video_path, video_dur = self._generate_video(
            script, task_id, style=style, identity_anchors=identity_anchors,
        )
        result.video_path = video_path
        result.video_duration = video_dur
        result.stages.append("video")

        if video_path:
            result.ok = True
        else:
            result.error = "视频生成失败"

        return result

    # ──────────────────────────────────────────────────────────────
    # 多阶段可干预流水线（借鉴 waoowaoo [A] 分阶段管线 + [D] 审核哲学）
    # ──────────────────────────────────────────────────────────────
    @staticmethod
    def _default_reviewer(stage: str, artifact: Dict[str, Any]) -> bool:
        """默认审核闸门：自动放行并记录（不谎报人工审核，仅作可干预钩子）。

        §0.7 白盒纪律：默认 reviewer 不等于「人工已审」，调用方若需真实人工门控
        须传入自己的 reviewer（返回 False 即停在该阶段）。
        """
        logger.info("[promote-gate] 阶段『%s』自动放行（默认 reviewer，未接人工审核）", stage)
        return True

    def promote_pipeline(self, goal: str, *, reviewer=None,
                         short_drama: bool = False,
                         identity_anchors: Optional[dict] = None,
                         style: str = "douyin", duration: int = 60) -> PromoteResult:
        """内容营销岗多阶段可干预流水线。

        阶段顺序: 选题 → 素材 → 分镜 → 配音 → 成片 → 分发。
        每阶段产出后必经 reviewer 闸门（§0.7 白盒审核），reviewer 返回 False 即
        停在该阶段并返回已产出的中间物，不静默假装跑完。
        reviewer(default=None) → 用内部 _default_reviewer（自动放行并记录）。
        底层能力走已接入商用/开源引擎（media.* / inference.llm / web.search），
        AOS 不自建生成引擎；缺能力时优雅降级（记 note，不停整体）。
        """
        reviewer = reviewer or self._default_reviewer
        out = PromoteResult(goal=goal)
        task_id = uuid.uuid4().hex[:8]

        # 1) 选题
        out.artifacts["选题"] = {"topic": goal}
        if not reviewer("选题", out.artifacts["选题"]):
            out.stopped_at = "选题"; return out
        out.stages_done.append("选题")

        # 2) 素材
        materials = self._search_materials(goal)
        out.artifacts["素材"] = {"materials": materials}
        if not reviewer("素材", out.artifacts["素材"]):
            out.stopped_at = "素材"; return out
        out.stages_done.append("素材")

        # 3) 分镜
        script = self._write_script(
            goal, materials, style=style, duration=duration,
            short_drama=short_drama, identity_anchors=identity_anchors,
        )
        out.artifacts["分镜"] = {"script": script}
        if not script or not reviewer("分镜", out.artifacts["分镜"]):
            out.stopped_at = "分镜"; return out
        out.stages_done.append("分镜")

        # 4) 配音（media.audio；缺则降级记录，不停整体）
        voice = self._unwrap(self._route("media.audio", {"text": script, "topic": goal})) or {}
        if not voice:
            voice = {"note": "media.audio 未配置，跳过配音（降级）"}
        out.artifacts["配音"] = voice
        if not reviewer("配音", out.artifacts["配音"]):
            out.stopped_at = "配音"; return out
        out.stages_done.append("配音")

        # 5) 成片（video 生成 + identity_anchors 一致性约束）
        video_path, video_dur = self._generate_video(
            script, task_id, style=style, identity_anchors=identity_anchors,
        )
        out.artifacts["成片"] = {"video_path": video_path, "video_duration": video_dur}
        if not video_path or not reviewer("成片", out.artifacts["成片"]):
            out.stopped_at = "成片"; return out
        out.stages_done.append("成片")

        # 6) 分发（content.distribute 多平台适配；缺则降级记录）
        dist = self._unwrap(self._route("content.distribute",
                                        {"topic": goal, "video_path": video_path, "style": style})) or {}
        if not dist:
            dist = {"note": "content.distribute 未配置，跳过分发（降级）"}
        out.artifacts["分发"] = dist
        if not reviewer("分发", out.artifacts["分发"]):
            out.stopped_at = "分发"; return out
        out.stages_done.append("分发")

        out.ok = True
        return out

    def _run_pipeline(self, topic: str, *, style: str, duration: int,
                     short_drama: bool, identity_anchors) -> InvokeResult:
        """把 promote_pipeline 包装成 InvokeResult（invoke 的 pipeline 分支用）。"""
        try:
            r = self.promote_pipeline(
                topic, short_drama=short_drama, identity_anchors=identity_anchors,
                style=style, duration=duration,
            )
            return InvokeResult(
                ok=r.ok,
                data={
                    "goal": r.goal,
                    "stages_done": r.stages_done,
                    "stopped_at": r.stopped_at,
                    "artifacts": r.artifacts,
                },
                engine_id=self.engine_id,
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"流水线异常: {e}", engine_id=self.engine_id)

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
                      style: str = "douyin", duration: int = 60,
                      short_drama: bool = False,
                      identity_anchors: Optional[dict] = None) -> str:
        """写视频脚本。优先用 LLM，不可用则用模板。"""
        materials_text = "\n".join(f"- {m}" for m in materials) if materials else "（无参考素材）"
        anchor_text = ""
        if identity_anchors:
            # 跨镜头一致性锚点（借鉴 waoowaoo [B]）：让 LLM 全程保持角色/场景特征
            anchor_text = (
                "\n角色/场景一致性锚点（务必全程保持，不得漂移）:\n"
                f"{json.dumps(identity_anchors, ensure_ascii=False)}\n"
            )

        # 短剧/漫剧模式（借鉴 waoowaoo [C]，opt-in）：强钩子强反转、留悬念续集
        if short_drama:
            base_prompt = (
                f"你是一个短剧/漫剧编剧。请围绕主题『{topic}』写一个强钩子、强反转的短剧脚本，"
                f"分 3-5 个分镜，每个分镜一段旁白，结尾留悬念引导续集。"
                f"{anchor_text}"
            )
        else:
            base_prompt = (
                f"你是一个短视频编剧。请为以下主题写一个约{duration}秒的{style}风格短视频脚本。\n\n"
                f"主题: {topic}\n\n"
                f"参考素材:\n{materials_text}\n"
                f"{anchor_text}"
                f"要求:\n"
                f"1. 分成3-5个分镜，每个分镜一段旁白\n"
                f"2. 开头要吸引人，结尾要有引导\n"
                f"3. 语言口语化，符合短视频节奏\n"
                f"4. 只输出分镜文本，每行一段，不要编号和格式\n"
            )

        # 尝试用 LLM 写脚本
        try:
            res = self._route("inference.llm", {"prompt": base_prompt})
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

    def _generate_video(self, script: str, task_id: str, *, style: str = "douyin",
                        identity_anchors: Optional[dict] = None) -> tuple:
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
                **({"identity_anchors": identity_anchors} if identity_anchors else {}),
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
