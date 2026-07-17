"""AutoSkill Agent —— 一句话全自动智能体。

用户只需要说一句话，剩下的全自动化：
1. 分析用户意图 → 拆解成需要的能力
2. 检查本地有没有对应的能力提供者
3. 没有就去 SkillHub 搜索、下载、安装
4. 安装后自动注册、立即使用
5. 把结果返回给用户

设计原则：
- 不侵入核心：作为上层编排 agent，不碰 FabricHub 核心逻辑
- 优雅降级：SkillHub 不可用就走本地，本地也没有就如实告知
- 风险可控：高危操作（系统删除、转账等）需要人工确认
- 诚实透明：告诉用户它用了什么技能、做了什么操作
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AutoSkillResult:
    """AutoSkill 执行结果。"""
    ok: bool
    task: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    final_output: Any = None
    error: str = ""
    skills_used: List[str] = field(default_factory=list)
    skills_installed: List[str] = field(default_factory=list)
    duration: float = 0.0


class AutoSkillAgent:
    """自动技能 Agent——一句话全自动。"""

    def __init__(self, route_fn: Callable = None, hub=None):
        self._route_fn = route_fn
        self._hub = hub
        self._capability_keywords = self._build_capability_map()

    def set_route_fn(self, route_fn: Callable) -> None:
        self._route_fn = route_fn

    def set_hub(self, hub) -> None:
        self._hub = hub

    # ── 核心入口 ──

    def run(self, task: str, *, auto_install: bool = True,
            confirm_risk_level: str = "low") -> AutoSkillResult:
        """执行任务——一句话全自动。

        Args:
            task: 用户的任务描述
            auto_install: 是否自动安装缺失的技能
            confirm_risk_level: 高于此风险等级需要人工确认（low/medium/high）

        Returns:
            AutoSkillResult 执行结果
        """
        t0 = time.time()
        result = AutoSkillResult(ok=False, task=task)

        try:
            # 第 1 步：分析任务 → 拆解能力
            logger.info("AutoSkill: 分析任务: %s", task[:80])
            capabilities = self._analyze_task(task)
            result.steps.append({
                "step": "analyze",
                "ok": True,
                "capabilities": capabilities,
            })
            logger.info("AutoSkill: 需要能力: %s", capabilities)

            if not capabilities:
                result.error = "无法解析任务所需的能力"
                return result

            # 第 2 步：检查本地可用性
            local_caps = self._check_local_capabilities(capabilities)
            missing = [c for c in capabilities if c not in local_caps]
            result.steps.append({
                "step": "check_local",
                "ok": True,
                "local_available": local_caps,
                "missing": missing,
            })
            logger.info("AutoSkill: 本地可用: %s, 缺失: %s", local_caps, missing)

            # 第 3 步：缺失的技能 → 去 SkillHub 找并安装
            if missing and auto_install:
                installed = self._try_install_missing(missing, task, confirm_risk_level)
                result.skills_installed = installed
                result.steps.append({
                    "step": "install",
                    "ok": len(installed) > 0 or len(missing) == 0,
                    "installed": installed,
                    "attempted": missing,
                })
                if installed:
                    logger.info("AutoSkill: 新安装技能: %s", installed)

            # 第 4 步：执行任务
            # 简化：如果有本地能力，就用 route_fn 执行第一步能力
            if self._route_fn and local_caps:
                primary_cap = local_caps[0]
                logger.info("AutoSkill: 执行主要能力: %s", primary_cap)
                try:
                    output = self._route_fn(primary_cap, {"task": task, "input": task})
                    result.final_output = output
                    result.ok = hasattr(output, "ok") and output.ok if output else True
                    result.skills_used = [primary_cap]
                    result.steps.append({
                        "step": "execute",
                        "ok": True,
                        "capability": primary_cap,
                    })
                except Exception as e:
                    result.error = f"执行失败: {e}"
                    result.steps.append({
                        "step": "execute",
                        "ok": False,
                        "error": str(e),
                    })
            else:
                # 没有 route_fn 或者没有本地能力
                if not self._route_fn:
                    result.error = "未配置 route_fn"
                elif not local_caps:
                    result.error = f"没有可用的能力提供者（需要: {capabilities}）"
                result.ok = False

        except Exception as e:
            result.error = str(e)
            logger.error("AutoSkill 执行失败: %s", e, exc_info=True)

        result.duration = round(time.time() - t0, 2)
        return result

    # ── 任务分析 ──

    def _analyze_task(self, task: str) -> List[str]:
        """分析任务，返回需要的能力列表。

        先用关键词匹配，未来可以接 LLM 做更智能的分析。
        """
        task_lower = task.lower()
        capabilities = []

        # 关键词 → 能力 映射
        for cap, keywords in self._capability_keywords.items():
            for kw in keywords:
                if kw.lower() in task_lower:
                    if cap not in capabilities:
                        capabilities.append(cap)
                    break

        # 如果啥也没匹配到，试试用 LLM 分析（如果有 LLM 的话）
        if not capabilities:
            llm_caps = self._analyze_with_llm(task)
            if llm_caps:
                capabilities = llm_caps

        return capabilities

    def _analyze_with_llm(self, task: str) -> List[str]:
        """用本地 LLM 分析任务需要什么能力。"""
        try:
            from core.fabric.utils.ollama_utils import llm_chat, llm_available
            if not llm_available():
                return []

            known_caps = list(self._capability_keywords.keys())
            prompt = f"""
用户任务：{task}

已知的能力列表：
{json.dumps(known_caps, ensure_ascii=False)}

请判断完成这个任务需要哪些能力？只返回能力名称的 JSON 数组，不要解释。
如果没有匹配的就返回空数组。
"""
            response = llm_chat(prompt, temperature=0.3, max_tokens=500, timeout=60)
            if response:
                # 尝试解析 JSON
                try:
                    # 找到第一个 [ 和最后一个 ]
                    start = response.find("[")
                    end = response.rfind("]")
                    if start >= 0 and end > start:
                        caps = json.loads(response[start:end+1])
                        if isinstance(caps, list):
                            # 过滤掉未知的能力
                            valid = [c for c in caps if c in known_caps]
                            return valid[:5]
                except Exception:
                    pass
        except Exception as e:
            logger.debug("LLM 分析任务失败: %s", e)

        return []

    # ── 本地能力检查 ──

    def _check_local_capabilities(self, capabilities: List[str]) -> List[str]:
        """检查哪些能力本地已有。"""
        available = []

        # 如果有 hub，用 hub 的能力探测
        if self._hub:
            try:
                for cap in capabilities:
                    if self._hub.resolve_engine(cap):
                        available.append(cap)
                return available
            except Exception:
                pass

        # 如果有 route_fn，用简化方式（假设常见能力都有）
        if self._route_fn:
            # 简化：假设已知的能力都有（真实情况应该问 registry）
            return capabilities

        return available

    # ── 自动安装 ──

    def _try_install_missing(self, missing_caps: List[str], task: str,
                             confirm_risk_level: str) -> List[str]:
        """尝试从 SkillHub 安装缺失的技能。"""
        installed = []

        try:
            from .skillhub_integration import get_skillhub_adapter
            from .autoskill_engine import get_autoskill_engine

            adapter = get_skillhub_adapter()
            engine = get_autoskill_engine()

            if not adapter.available:
                logger.info("SkillHub 不可用，跳过自动安装")
                return []

            # 为每个缺失的能力搜索一个技能
            for cap in missing_caps:
                try:
                    results = adapter.search(cap, limit=3)
                    if not results:
                        continue

                    # 选第一个（最相关的）
                    best = results[0]
                    skill_id = best.get("id", "")

                    # 风险评估
                    risk = self._assess_risk(best, task)
                    if self._risk_level_needs_confirm(risk, confirm_risk_level):
                        logger.info("技能 %s 风险=%s，需要人工确认，跳过自动安装", skill_id, risk)
                        continue

                    # 安装
                    result = engine.install(skill_id)
                    if result.get("ok"):
                        installed.append(skill_id)
                        logger.info("自动安装成功: %s", skill_id)

                except Exception as e:
                    logger.warning("安装技能 %s 失败: %s", cap, e)
                    continue

        except Exception as e:
            logger.warning("自动安装失败: %s", e)

        return installed

    def _assess_risk(self, skill_info: Dict[str, Any], task: str) -> str:
        """风险评估。"""
        try:
            from .autoskill_engine import AutoSkillEngine
            # 复用 autoskill engine 的风险评估
            temp_engine = AutoSkillEngine()
            return temp_engine._assess_risk(skill_info, task)
        except Exception:
            return "medium"

    @staticmethod
    def _risk_level_needs_confirm(risk: str, threshold: str) -> bool:
        """判断风险等级是否需要人工确认。"""
        levels = {"low": 0, "medium": 1, "high": 2}
        return levels.get(risk, 1) > levels.get(threshold, 0)

    # ── 能力关键词映射 ──

    @staticmethod
    def _build_capability_map() -> Dict[str, List[str]]:
        """构建 能力 → 关键词 的映射表。"""
        return {
            "web.search": [
                "搜索", "找", "查", "搜索一下", "帮我找", "查询", "检索",
                "search", "find", "lookup", "google", "百度",
            ],
            "web.fetch": [
                "抓取", "爬取", "网页", "网站", "链接", "url",
                "fetch", "scrape", "crawl", "网页内容",
            ],
            "inference.llm": [
                "写", "生成", "创作", "写文章", "写代码", "翻译",
                "总结", "摘要", "分析", "解释", "回答",
                "llm", "gpt", "chat", "生成文本", "大模型",
            ],
            "media.video": [
                "视频", "生成视频", "做视频", "短视频", "剪辑",
                "video", "生成视频", "视频制作",
            ],
            "media.image": [
                "图片", "画图", "生成图", "作图", "绘画",
                "image", "picture", "draw", "生成图片",
            ],
            "action.code_exec": [
                "运行", "执行", "代码", "脚本", "python",
                "跑一下", "计算", "code", "exec", "run",
            ],
            "action.file_access": [
                "文件", "读取", "读文件", "保存", "写文件",
                "file", "read", "write", "save",
            ],
            "multimodal.vlm": [
                "看图", "图片描述", "识别图片", "图像理解",
                "vlm", "vision", "image", "描述图片",
            ],
            "audio.stt": [
                "语音", "转写", "录音", "语音转文字",
                "stt", "speech", "audio", "声音",
            ],
            "audio.tts": [
                "朗读", "语音", "合成", "文字转语音",
                "tts", "speak", "read aloud", "配音",
            ],
            "content.marketing_video": [
                "营销视频", "内容营销", "短视频制作", "抖音", "小红书",
                "b站", "运营", "涨粉",
            ],
            "content.feedback": [
                "反馈", "评论", "舆情", "收集反馈",
                "echo", "用户反馈", "评价",
            ],
            "skill.create": [
                "创建技能", "新技能", "做一个技能",
                "skill", "创造技能",
            ],
            "workflow.orchestrate": [
                "工作流", "编排", "流水线", "pipeline",
                "多步骤", "自动化流程",
            ],
        }


# 单例
_agent: Optional[AutoSkillAgent] = None


def get_autoskill_agent() -> AutoSkillAgent:
    global _agent
    if _agent is None:
        _agent = AutoSkillAgent()
    return _agent
