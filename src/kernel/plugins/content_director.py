"""内容生产流水线导演（ContentDirector）—— AOS 自主内容生产闭环。

用户只给一句话目标（goal），导演自主跑完整条链路：
  1. 找内容  → 经 hub 路由 web.search 检索素材（沙箱无网则降级空素材，不谎报）
  2. 分析    → 经 hub 路由 inference.llm 真思考抽主题/受众/调性（无 LLM 时诚实降级规则版）
  3. 写剧本  → 经 hub 路由 inference.llm 真编剧生成 script.md（无 LLM 时降级模板）
  4. 导演    → 拆镜头，为每个镜头构造 ComfyIntent，**自己改节点图**
              （动态插入 LoRA/ControlNet 并重连，复用 ComfyUIDirector）
  5. 调工具  → 经 hub 路由 media.image/media.video 出图出视频、code.generate 出配套脚本
  6. 审核包  → 组装 HandoffEnvelope 落 reviews/ + 调 IMA store_handoff（有 key 真写）
  7. 发布    → **默认停在审核**（human-in-the-loop）；approve(review_id) 才把草稿
              落 published/ 并记 IMA 发布，实现「审核后自己发布」

设计原则（对齐 AGENTS.md / 九大理念）：
- 复用而非重写：route_fn 直接复用 FabricHub 单一可信路由（与 OrchestrationChiplet 同构）；
  ComfyUI 动态编排复用 ComfyUIDirector；审核/发布复用 handoff + IMA。
- 诚实降级：检索/出图无网络或 ComfyUI 不可达时如实返回降级产物，不伪造成功。
- 不自动越过审核：生产完停在审核包，发布必须显式 approve（理念6 可验证即真理）。
"""
from __future__ import annotations

import os
import re
import json
import uuid
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from skills.comfyui import ComfyUIDirector, ComfyIntent
from core.fabric.handoff import HandoffEnvelope, store_handoff
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)


@dataclass
class ProductionResult:
    """一次内容生产的完整结果（含各阶段产物路径，便于审计/回放）。"""
    task_id: str
    goal: str
    stages: List[str] = field(default_factory=list)
    materials: List[str] = field(default_factory=list)
    analysis: Dict[str, Any] = field(default_factory=dict)
    script_path: str = ""
    shots: List[Dict[str, Any]] = field(default_factory=list)
    review_id: str = ""
    review_path: str = ""
    published: bool = False
    published_path: str = ""
    artifacts: List[str] = field(default_factory=list)


@dataclass
class PublishResult:
    task_id: str
    review_id: str
    ok: bool
    published_path: str = ""
    ima_stored: bool = False
    error: str = ""


# 镜头关键词 → 导演自主决定的风格 / LoRA / ControlNet（演示「自己改节点图」）
_STYLE_RULES = [
    ("赛博朋克", "cyberpunk", ["cyberpunk.safetensors"], []),
    ("cyberpunk", "cyberpunk", ["cyberpunk.safetensors"], []),
    ("动漫", "anime", ["anime.safetensors"], []),
    ("anime", "anime", ["anime.safetensors"], []),
    ("写实", "photoreal", ["realistic.safetensors"], []),
    ("肖像", "portrait", [], ["openpose"]),
    ("人像", "portrait", [], ["openpose"]),
    ("portrait", "portrait", [], ["openpose"]),
    ("电影感", "cinematic", ["cinematic.safetensors"], []),
    ("风景", "landscape", [], ["depth"]),
    ("产品", "product", [], ["canny"]),
]


class ContentDirector(BaseAgentAdapter):
    """一句话目标 → 自主内容生产（检索/分析/剧本/导演/工具/审核/发布）。"""

    engine_id = "content-director"

    def __init__(self, route_fn: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
                 work_root: str = "", llm=None) -> None:
        super().__init__()
        # route_fn: (capability:str, payload:dict) -> InvokeResult|dict，由 FabricHub 注入。
        self._route_fn = route_fn
        # 运行时产物默认落仓库根下的 _content_work/（已被 .gitignore 忽略），
        # 不再污染仓库根目录；可用 env AOS_CONTENT_WORK_ROOT 覆盖。
        self._work_root = work_root or os.environ.get(
            "AOS_CONTENT_WORK_ROOT",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "_content_work"))
        self._llm = llm  # 主机有 LLM 时注入，升级分析与剧本质量
        self._director = ComfyUIDirector(llm_planner=None)  # 节点编排（沙箱规则版）

    # ── 目录 ────────────────────────────────────────────────
    def _dir(self, name: str) -> str:
        p = os.path.join(self._work_root, name)
        os.makedirs(p, exist_ok=True)
        return p

    # ── FabricHub 适配器接口 ───────────────────────────────
    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_PRODUCE]

    def health(self) -> bool:
        # 导演复用 hub 路由；route_fn 已注入即健康，自身无重型依赖。
        return self._route_fn is not None

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: "InvokeRequest") -> "InvokeResult":
        """hub.route("content.produce", {goal}) 入口：一句话触发整条自主生产。"""
        if hasattr(req, "payload") and req.payload:
            payload = req.payload
        else:
            payload = {}
        goal = (payload.get("goal") or "").strip()
        if not goal:
            return InvokeResult(ok=False, error="缺少 goal", engine_id=self.engine_id)
        auto_publish = bool(payload.get("auto_publish", False))
        try:
            res = self.produce(goal, auto_publish=auto_publish)
            return InvokeResult(ok=True, data={
                "task_id": res.task_id, "goal": res.goal, "stages": res.stages,
                "script_path": res.script_path, "shots": res.shots,
                "review_id": res.review_id, "review_path": res.review_path,
                "published": res.published,
            }, engine_id=self.engine_id)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"content produce failed: {e}",
                                engine_id=self.engine_id)

    # ── 主入口 ─────────────────────────────────────────────
    def produce(self, goal: str, *, auto_publish: bool = False) -> ProductionResult:
        """自主跑完整条内容生产链路，默认停在审核（不自动发布）。"""
        task_id = uuid.uuid4().hex[:8]
        res = ProductionResult(task_id=task_id, goal=goal)

        # 1) 找内容
        materials = self._gather(goal)
        res.materials = materials
        res.stages.append("gather")

        # 2) 分析
        analysis = self._analyze(goal, materials)
        res.analysis = analysis
        res.stages.append("analyze")

        # 3) 写剧本
        script_path = os.path.join(self._dir("drafts"), task_id, "script.md")
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(self._write_script(goal, analysis, materials))
        res.script_path = script_path
        res.stages.append("write_script")

        # 4) 导演：拆镜头 + 每个镜头自己构造意图、自己改节点图
        shots_dir = os.path.join(self._dir("drafts"), task_id, "shots")
        os.makedirs(shots_dir, exist_ok=True)
        shots = self._direct(goal, analysis)
        for i, shot in enumerate(shots):
            intent: ComfyIntent = shot["intent"]
            # 导演自己把节点图拼出来（动态编排），落盘供审计（验证「自己改节点图」）
            wf = self._director.build_workflow(intent)
            wf_path = os.path.join(shots_dir, f"shot_{i:02d}_workflow.json")
            with open(wf_path, "w", encoding="utf-8") as f:
                json.dump(wf, f, ensure_ascii=False, indent=2)
            # 5) 调工具：经 hub 路由出图/出视频
            out_path = self._render_shot(intent, i)
            shot_rec = {
                "index": i,
                "shot_prompt": intent.prompt,
                "action": intent.action,
                "loras": intent.loras,
                "controlnets": intent.controlnets,
                "workflow_node_count": len(wf),
                "workflow_path": wf_path,
                "output_path": out_path,
            }
            shots[i] = shot_rec
            res.artifacts.append(out_path or "")
        res.shots = shots
        res.stages.append("direct")
        res.stages.append("execute")

        # 6) 审核包（human-in-the-loop 停点）
        review_path = self._build_review(res)
        res.review_path = review_path
        res.review_id = task_id
        res.stages.append("review")

        # 7) 发布（默认不自动；auto_publish 仅用于无人值守流水线）
        if auto_publish:
            pub = self.approve(task_id)
            res.published = pub.ok
            res.published_path = pub.published_path

        return res

    # ── 阶段实现 ──────────────────────────────────────────
    def _gather(self, goal: str) -> List[str]:
        """找内容：经 hub 路由 web.search 检索素材。无 route_fn / 无网则降级。"""
        if self._route_fn is None:
            return []
        try:
            out = self._route_fn("web.search", {"query": goal, "max_results": 5})
            data = self._unwrap(out)
            items = data.get("results") or data.get("items") or []
            return [it.get("title", "") + " " + it.get("url", "") for it in items] or \
                   [f"[检索返回] {data.get('content', '')[:200]}" if data.get("content") else ""]
        except Exception as e:  # noqa: BLE001
            logger.warning("检索素材失败（降级空素材，不谎报）: %s", e)
            return []

    # ── LLM 思考（复用 hub 单一可信路由 inference.llm，不自造 LLM）──────────
    def _llm_think(self, system: str, user: str) -> Optional[str]:
        """经 hub 路由 inference.llm 真正思考；无 route_fn / 失败则返 None（诚实降级）。"""
        if self._llm is not None and callable(self._llm):
            try:
                return self._llm(system=system, user=user)
            except Exception as e:  # noqa: BLE001
                logger.warning("注入式 llm 失败，尝试 inference.llm 路由: %s", e)
        if self._route_fn is None:
            return None
        try:
            out = self._route_fn("inference.llm", {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            })
            data = self._unwrap(out)
            text = (
                data.get("text")
                or data.get("content")
                or data.get("output")
                or (data.get("choices", [{}])[0]
                    .get("message", {}).get("content", ""))
            )
            return text.strip() or None
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM 思考失败（降级规则版）: %s", e)
            return None

    @staticmethod
    def _extract_json(text: str) -> Any:
        """从 LLM 文本里抠出第一个 JSON 对象/数组（兼容 ```json 围栏）。"""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except Exception:
            pass
        m = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
        return None

    def _analyze(self, goal: str, materials: List[str]) -> Dict[str, Any]:
        """分析目标与素材，抽主题/受众/调性。优先走 inference.llm 真思考，失败回退规则。"""
        mats = "\n".join(f"- {m}" for m in materials) or "（无外部素材）"
        prompt = (
            f"你是内容策略分析师。请分析以下创作目标并输出结构化结论。\n"
            f"目标：{goal}\n参考素材：\n{mats}\n\n"
            f"只输出 JSON，字段：theme(主题) / audience(受众) / tone(调性:cinematic|"
            f"natural|playful|serious) / key_message(核心信息) / visual_style(视觉风格建议)。"
        )
        llm_out = self._llm_think(
            "你是严谨的内容策略分析师，只输出 JSON，不要任何解释。", prompt)
        if llm_out:
            parsed = self._extract_json(llm_out)
            if isinstance(parsed, dict) and parsed:
                parsed["material_count"] = len(materials)
                parsed.setdefault("theme", goal)
                return parsed
            # LLM 有返回但解析不出 JSON：保留原始文本，不丢信息
            return {"theme": goal, "tone": "natural", "audience": "general",
                    "material_count": len(materials), "llm_raw": llm_out}
        # 降级规则版（无 LLM / 调用失败，诚实回落）
        p = goal.lower()
        tone = "cinematic" if any(k in p for k in ["电影", "cinematic", "大片"]) else "natural"
        audience = "general"
        if any(k in p for k in ["儿童", "kid", "童"]):
            audience = "children"
        elif any(k in p for k in ["专业", "tech", "技术", "学术"]):
            audience = "professional"
        return {
            "theme": goal,
            "tone": tone,
            "audience": audience,
            "material_count": len(materials),
        }

    def _write_script(self, goal: str, analysis: Dict[str, Any], materials: List[str]) -> str:
        """写剧本：分场/分镜/视觉描述。优先走 inference.llm 真编剧，失败回退模板。"""
        analysis_json = json.dumps(analysis, ensure_ascii=False)
        mats = "\n".join(f"- {m}" for m in materials) or "- （无外部素材，纯原创）"
        prompt = (
            f"你是专业短视频/广告剧本编剧。基于以下分析与素材，写一页分场剧本。\n"
            f"创作目标：{goal}\n分析结果：{analysis_json}\n参考素材：\n{mats}\n\n"
            f"输出 Markdown：含『分析』『参考素材』『分场（每场：画面描述+旁白/台词）』。"
        )
        llm_out = self._llm_think(
            "你是专业内容编剧，输出结构清晰的中文 Markdown 剧本。", prompt)
        if llm_out and len(llm_out.strip()) > 20:
            return f"# 内容剧本：{goal}\n\n{llm_out.strip()}\n"
        # 降级模板（无 LLM / 返回过短）
        mats_block = "\n".join(f"- {m}" for m in materials) or "- （无外部素材，纯原创）"
        return (
            f"# 内容剧本：{goal}\n\n"
            f"## 分析\n"
            f"- 主题：{analysis.get('theme','')}\n"
            f"- 调性：{analysis.get('tone','')}\n"
            f"- 受众：{analysis.get('audience','')}\n\n"
            f"## 参考素材\n{mats_block}\n\n"
            f"## 分场\n"
            f"**场1｜主视觉**\n"
            f"- 画面：{goal}，电影感构图，主体突出。\n"
            f"- 台词/旁白：（待录制）\n\n"
            f"**场2｜细节特写**\n"
            f"- 画面：{goal} 的关键细节放大，强化质感。\n"
            f"- 台词/旁白：（待录制）\n"
        )

    def _direct(self, goal: str, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """导演：拆镜头，并为每个镜头自己构造意图（含自主决定的 LoRA/ControlNet）。"""
        p = goal.lower()
        style = ""
        loras: List[str] = []
        controlnets: List[str] = []
        for kw, st, lo, cn in _STYLE_RULES:
            if kw in p:
                style = st
                loras = list(lo)
                controlnets = list(cn)
                break
        motion = any(k in p for k in ["动", "视频", "motion", "短片", "动画"])
        has_image = False  # 自产内容，无输入图 → 文生图/文生视频

        shots: List[Dict[str, Any]] = []
        # 场1：主视觉（导演自主加风格 LoRA / 人像 ControlNet）
        shots.append({
            "intent": ComfyIntent(
                prompt=f"{goal}，{style} 风格，高清细节" if style else goal,
                has_image=has_image,
                motion=motion,
                style=style,
                loras=loras,
                controlnets=controlnets,
                action="img2vid" if (motion or has_image) else "txt2img",
                width=1024, height=768,
            )
        })
        # 场2：细节特写（复用同一意图族，强化质感）
        shots.append({
            "intent": ComfyIntent(
                prompt=f"{goal} 的细节特写，质感强化",
                has_image=has_image,
                motion=motion,
                style=style,
                loras=loras,
                controlnets=controlnets,
                action="img2vid" if (motion or has_image) else "txt2img",
                width=768, height=768,
            )
        })
        return shots

    def _render_shot(self, intent: ComfyIntent, index: int) -> str:
        """调工具：经 hub 路由 media.image / media.video 出图出视频。"""
        if self._route_fn is None:
            # 无路由：落占位产物（仍真实记录意图，不伪造成功出图）
            out = os.path.join(self._dir("drafts"), "_placeholder",
                               f"shot_{index:02d}.txt")
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                f.write(json.dumps(intent.to_dict(), ensure_ascii=False))
            return out
        cap = "media.video" if intent.action in ("img2vid", "vid2vid") else "media.image"
        try:
            out = self._route_fn(cap, {"intent": intent.to_dict()})
            data = self._unwrap(out)
            return data.get("output_path") or ""
        except Exception as e:  # noqa: BLE001
            logger.warning("渲染镜头 %d 失败（降级占位）: %s", index, e)
            return ""

    def _confidence(self, res: ProductionResult) -> str:
        """量化置信（原则6 三级）：检索素材数 + 真实产物数驱动，诚实反映降级。"""
        n_mat = len(res.materials)
        n_shots = len(res.shots)
        n_out = sum(1 for s in res.shots if s.get("output_path"))
        if n_mat >= 5 and n_shots and n_out == n_shots:
            return "high"
        if n_mat >= 1 or n_out > 0:
            return "medium"
        return "low"

    def _build_review(self, res: ProductionResult) -> str:
        """组装审核包（HandoffEnvelope）→ 落 reviews/ + 调 IMA store_handoff。"""
        facts = [f"剧本：{res.script_path}"]
        for s in res.shots:
            facts.append(
                f"镜头{s['index']}｜{s['action']}｜LoRA={s['loras']}｜"
                f"ControlNet={s['controlnets']}｜节点数={s['workflow_node_count']}｜"
                f"产物={s['output_path'] or '（降级占位）'}")
        conf = self._confidence(res)
        env = HandoffEnvelope(
            task_id=res.task_id,
            title=f"内容生产审核：{res.goal}",
            summary=f"已自主完成检索/分析/剧本/导演/出图，共 {len(res.shots)} 个镜头待审核发布。",
            confirmed_facts=facts,
            assumptions=[f"调性={res.analysis.get('tone')}，受众={res.analysis.get('audience')}"],
            risk_boundary=[
                "AI 生成内容需人工审核后发布，禁止自动越过审核节点。",
                "含人物/品牌时核对肖像权与商标授权。",
            ],
            handoff_to="人工审核（人）",
            source="ContentDirector",
            confidence=conf,
            tags=["content_production", "review"],
        )
        review_dir = self._dir("reviews")
        review_path = os.path.join(review_dir, f"{res.task_id}.md")
        with open(review_path, "w", encoding="utf-8") as f:
            f.write(env.to_markdown())
        # 发布交接记录（有 IMA key 真写，无则诚实失败不谎报）
        try:
            store_handoff(env)
        except Exception as e:  # noqa: BLE001
            logger.info("审核包 IMA 记录跳过（未配置 key 或网络不可达）: %s", e)
        return review_path

    # ── 发布（审核后自己发布）──────────────────────────────
    @staticmethod
    def _unwrap(out):
        """兼容 route_fn 返回 InvokeResult(.data) / {ok,data} dict / 纯 data。"""
        if hasattr(out, "data"):
            return out.data
        if isinstance(out, dict) and "data" in out:
            return out["data"]
        return out

    def approve(self, review_id: str, *, notes: str = "") -> PublishResult:
        """审核通过 → 把草稿落 published/ 并记 IMA 发布（human-in-the-loop 解锁）。"""
        draft_dir = os.path.join(self._work_root, "drafts", review_id)
        review_path = os.path.join(self._work_root, "reviews", f"{review_id}.md")
        if not os.path.isdir(draft_dir) or not os.path.isfile(review_path):
            return PublishResult(task_id=review_id, review_id=review_id, ok=False,
                                 error="审核包不存在，无法发布")
        pub_dir = os.path.join(self._dir("published"), review_id)
        os.makedirs(pub_dir, exist_ok=True)
        # 复制草稿产物到发布区
        for root, _, files in os.walk(draft_dir):
            for fn in files:
                src = os.path.join(root, fn)
                rel = os.path.relpath(src, draft_dir)
                dst = os.path.join(pub_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(src, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(content)
        manifest = {
            "task_id": review_id,
            "approved_at": _now(),
            "notes": notes,
            "artifacts": [
                os.path.join(pub_dir, "shots", f)
                for f in os.listdir(os.path.join(pub_dir, "shots"))
                if f.endswith(".json") or f.endswith(".txt")
            ],
        }
        with open(os.path.join(pub_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        # 记 IMA 发布（有 key 真写，无则诚实失败不谎报）
        ima_stored = False
        try:
            env = HandoffEnvelope(
                task_id=review_id,
                title=f"内容已发布：{review_id}",
                summary=f"审核通过，已发布至 {pub_dir}",
                confirmed_facts=[f"发布目录：{pub_dir}"],
                handoff_to="发布归档",
                source="ContentDirector.approve",
                tags=["content_production", "published"],
            )
            r = store_handoff(env)
            ima_stored = bool(r and r.get("success"))
        except Exception as e:  # noqa: BLE001
            logger.info("发布 IMA 记录跳过（未配置 key 或网络不可达）: %s", e)

        return PublishResult(task_id=review_id, review_id=review_id, ok=True,
                             published_path=pub_dir, ima_stored=ima_stored)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


_content_director_instance: Optional["ContentDirector"] = None


def get_content_director(route_fn: Optional[Callable[[str, Dict[str, Any]], Any]] = None) -> "ContentDirector":
    """内容生产导演单例（复用 hub 路由）。route_fn 仅首次构造时注入。"""
    global _content_director_instance
    if _content_director_instance is None:
        _content_director_instance = ContentDirector(route_fn=route_fn)
    return _content_director_instance


__all__ = ["ContentDirector", "ProductionResult", "PublishResult", "get_content_director"]
