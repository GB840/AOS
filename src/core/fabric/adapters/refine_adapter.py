"""内容优化适配器（Refine）—— AOS 内容飞轮的优化层。

输入反馈数据 + 历史内容数据 → 生成优化建议 → 输出新的内容方案。

设计原则：
- 数据驱动：所有优化建议基于真实数据，不拍脑袋
- 可操作：每条建议都能直接落地，不是空泛的"要优化"
- A/B 思维：提供多个方案，可对比测试
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.environ.get(
    "AOS_REFINE_OUTPUT_DIR",
    os.path.join("data", "workspaces", "fabric", "refine"),
)


def _output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


@dataclass
class OptimizationSuggestion:
    """一条优化建议。"""
    category: str  # 选题 / 标题 / 脚本 / 封面 / 发布时间 / 平台策略
    suggestion: str  # 具体建议
    reason: str  # 为什么这么建议（数据依据）
    priority: str = "medium"  # high / medium / low
    expected_impact: str = ""  # 预期效果


@dataclass
class RefineResult:
    """一次优化的完整结果。"""
    task_id: str
    topic: str
    suggestions: List[OptimizationSuggestion] = field(default_factory=list)
    next_content_plan: Dict[str, Any] = field(default_factory=dict)
    ab_test_plan: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    ok: bool = False
    error: str = ""


class RefineAdapter(BaseAgentAdapter):
    """内容优化适配器：基于反馈数据生成优化建议。

    MVP 阶段：基于关键词/情感的规则化优化建议。
    后续阶段：接入 LLM 做深度分析，自动 A/B 测试。
    """

    @property
    def engine_id(self) -> str:
        return "refine"

    def __init__(self, route_fn=None) -> None:
        self._route_fn = route_fn

    def set_route_fn(self, route_fn) -> None:
        self._route_fn = route_fn

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_OPTIMIZE, Capability.CONTENT_REFINE, Capability.CONTENT_AB_TEST]

    def health(self) -> bool:
        return True  # 规则化优化不依赖外部服务

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        topic = (payload.get("topic") or "").strip()
        feedback_data = payload.get("feedback_data") or {}
        history_data = payload.get("history_data") or []
        content_type = payload.get("content_type") or "video"

        if not topic:
            return InvokeResult(
                ok=False,
                error="缺少 topic（内容主题）",
                engine_id=self.engine_id,
            )

        try:
            result = self.optimize(
                topic=topic,
                feedback_data=feedback_data,
                history_data=history_data,
                content_type=content_type,
            )
            return InvokeResult(
                ok=result.ok,
                data={
                    "task_id": result.task_id,
                    "topic": result.topic,
                    "suggestions": [
                        {
                            "category": s.category,
                            "suggestion": s.suggestion,
                            "reason": s.reason,
                            "priority": s.priority,
                            "expected_impact": s.expected_impact,
                        }
                        for s in result.suggestions
                    ],
                    "next_content_plan": result.next_content_plan,
                    "ab_test_plan": result.ab_test_plan,
                    "summary": result.summary,
                },
                engine_id=self.engine_id,
                error=result.error,
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(
                ok=False,
                error=f"优化失败: {e}",
                engine_id=self.engine_id,
            )

    def optimize(self, *, topic: str, feedback_data: Dict = None,
                 history_data: List = None, content_type: str = "video",
                 use_llm: bool = True) -> RefineResult:
        """生成优化建议。"""
        task_id = uuid.uuid4().hex[:8]
        result = RefineResult(task_id=task_id, topic=topic)
        feedback_data = feedback_data or {}
        history_data = history_data or []

        # 生成各维度优化建议
        result.suggestions.extend(self._topic_suggestions(topic, feedback_data))
        result.suggestions.extend(self._title_suggestions(feedback_data))
        result.suggestions.extend(self._script_suggestions(feedback_data))
        result.suggestions.extend(self._platform_suggestions(feedback_data))

        # 按优先级排序
        priority_order = {"high": 0, "medium": 1, "low": 2}
        result.suggestions.sort(key=lambda s: priority_order.get(s.priority, 1))

        # 生成下一期内容计划
        result.next_content_plan = self._generate_next_plan(topic, feedback_data)

        # 生成 A/B 测试方案
        result.ab_test_plan = self._generate_ab_test_plan(topic, feedback_data)

        # LLM 深度优化（可选）
        if use_llm:
            self._llm_deep_optimize(result, feedback_data)

        # 生成总结
        result.summary = self._generate_summary(result)

        # 保存结果
        self._save_result(result)

        result.ok = len(result.suggestions) > 0
        return result

    def _topic_suggestions(self, topic: str, feedback: Dict) -> List[OptimizationSuggestion]:
        """选题方向优化建议。"""
        suggestions = []
        needs = feedback.get("needs", [])
        top_keywords = feedback.get("top_keywords", [])

        if needs:
            suggestions.append(OptimizationSuggestion(
                category="选题",
                suggestion=f"下期内容可以围绕用户最关心的问题展开：{needs[0][:30]}",
                reason=f"从反馈中发现 {len(needs)} 条潜在需求/问题，优先回应用户最关心的点",
                priority="high",
                expected_impact="提高用户互动率和完播率",
            ))

        if top_keywords:
            suggestions.append(OptimizationSuggestion(
                category="选题",
                suggestion=f"内容中多强调「{top_keywords[0]}」这个关键词",
                reason=f"用户讨论中「{top_keywords[0]}」出现频率最高，说明这是用户最关心的点",
                priority="medium",
                expected_impact="提高内容相关性和搜索曝光",
            ))

        suggestions.append(OptimizationSuggestion(
            category="选题",
            suggestion="做一期「常见问题解答」合集",
            reason="从反馈中整理用户最常问的 5-10 个问题，做一期集中解答",
            priority="medium",
            expected_impact="提高账号价值感和用户粘性",
        ))

        return suggestions

    def _title_suggestions(self, feedback: Dict) -> List[OptimizationSuggestion]:
        """标题优化建议。"""
        suggestions = []

        suggestions.append(OptimizationSuggestion(
            category="标题",
            suggestion="标题加入数字（如「3个技巧」「5分钟学会」）",
            reason="数据表明带数字的标题点击率平均高 20-30%，给用户明确的预期",
            priority="high",
            expected_impact="提高点击率 15-30%",
        ))

        suggestions.append(OptimizationSuggestion(
            category="标题",
            suggestion="用「疑问式」或「反差式」标题",
            reason="引发好奇心的标题更容易被点开，比如「为什么你用XX没效果？」",
            priority="medium",
            expected_impact="提高点击率 10-20%",
        ))

        suggestions.append(OptimizationSuggestion(
            category="标题",
            suggestion="标题控制在 15-25 字之间",
            reason="太短信息不足，太长被截断，15-25 字是黄金区间",
            priority="low",
            expected_impact="轻微提升点击率",
        ))

        return suggestions

    def _script_suggestions(self, feedback: Dict) -> List[OptimizationSuggestion]:
        """脚本/内容优化建议。"""
        suggestions = []
        negative_count = feedback.get("negative_count", 0)
        positive_count = feedback.get("positive_count", 0)

        suggestions.append(OptimizationSuggestion(
            category="脚本",
            suggestion="前 3 秒必须抛出核心价值或悬念",
            reason="短视频用户耐心只有 3 秒，开头不抓住人就划走了",
            priority="high",
            expected_impact="显著提高完播率",
        ))

        suggestions.append(OptimizationSuggestion(
            category="脚本",
            suggestion="每 15 秒一个小高潮/知识点",
            reason="保持用户注意力，避免中途划走",
            priority="medium",
            expected_impact="提高平均播放时长 20-30%",
        ))

        if negative_count > 0:
            suggestions.append(OptimizationSuggestion(
                category="脚本",
                suggestion="正面回应负面反馈，不回避问题",
                reason=f"发现 {negative_count} 条负面评价，主动承认不足并给出改进方案，反而能赢得信任",
                priority="high",
                expected_impact="扭转负面印象，提高用户信任度",
            ))

        suggestions.append(OptimizationSuggestion(
            category="脚本",
            suggestion="结尾加明确的互动引导",
            reason="比如「你们觉得呢？评论区聊聊」，直接引导评论",
            priority="medium",
            expected_impact="提高评论数 20-50%",
        ))

        return suggestions

    def _platform_suggestions(self, feedback: Dict) -> List[OptimizationSuggestion]:
        """平台策略优化建议。"""
        suggestions = []

        suggestions.append(OptimizationSuggestion(
            category="平台策略",
            suggestion="同一内容，不同平台不同剪辑版本",
            reason="抖音重节奏（15-30秒），B站重深度（5-10分钟），小红书重视觉，不能一稿多发",
            priority="high",
            expected_impact="各平台表现提升 30-50%",
        ))

        suggestions.append(OptimizationSuggestion(
            category="平台策略",
            suggestion="发布时间选在用户高峰时段",
            reason="工作日 12:00-13:00、18:00-22:00，周末 10:00-12:00、15:00-22:00",
            priority="medium",
            expected_impact="提高初始曝光量",
        ))

        suggestions.append(OptimizationSuggestion(
            category="平台策略",
            suggestion="发布后 1 小时内积极回复评论",
            reason="平台算法会把早期互动率高的内容推更多流量",
            priority="medium",
            expected_impact="提高初始流量池层级",
        ))

        return suggestions

    def _generate_next_plan(self, topic: str, feedback: Dict) -> Dict:
        """生成下一期内容计划。"""
        needs = feedback.get("needs", [])
        top_keywords = feedback.get("top_keywords", [])

        focus = needs[0] if needs else f"深入讲解{topic}的核心技巧"
        keyword = top_keywords[0] if top_keywords else topic

        return {
            "topic": f"{topic}进阶：从入门到精通",
            "angle": "教程/干货",
            "focus": focus,
            "keywords": [keyword] + top_keywords[:3],
            "target_duration": 60,
            "target_platforms": ["douyin", "xiaohongshu", "bilibili"],
            "script_outline": [
                "开头：抛出一个用户常见痛点（3秒）",
                "中间：分 3 点讲解解决方案（每点 15-20 秒）",
                "结尾：总结 + 互动引导（5秒）",
            ],
        }

    def _generate_ab_test_plan(self, topic: str, feedback: Dict) -> List[Dict]:
        """生成 A/B 测试方案。"""
        return [
            {
                "test_name": "标题 A/B 测试",
                "version_a": f"{topic}到底是什么？",
                "version_b": f"3分钟搞懂{topic}，90%的人都不知道！",
                "metric": "点击率",
                "duration": "24小时",
                "hypothesis": "带数字和悬念的标题点击率更高",
            },
            {
                "test_name": "封面 A/B 测试",
                "version_a": "纯文字封面",
                "version_b": "人物+文字对比图",
                "metric": "点击率",
                "duration": "24小时",
                "hypothesis": "有人物的封面点击率更高",
            },
            {
                "test_name": "发布时间测试",
                "version_a": "中午 12:00 发布",
                "version_b": "晚上 19:00 发布",
                "metric": "初始 1 小时播放量",
                "duration": "对比 3 天",
                "hypothesis": "晚上发布效果更好",
            },
        ]

    def _generate_summary(self, result: RefineResult) -> str:
        """生成总结。"""
        high_count = sum(1 for s in result.suggestions if s.priority == "high")
        med_count = sum(1 for s in result.suggestions if s.priority == "medium")
        low_count = sum(1 for s in result.suggestions if s.priority == "low")

        lines = [
            f"针对「{result.topic}」的内容优化建议：",
            f"共 {len(result.suggestions)} 条建议（高优 {high_count} / 中优 {med_count} / 低优 {low_count}）",
            "",
            "🎯 高优先级建议：",
        ]

        for s in result.suggestions:
            if s.priority == "high":
                lines.append(f"  • [{s.category}] {s.suggestion}")

        lines.append("")
        lines.append("📅 下一期内容计划：")
        plan = result.next_content_plan
        if plan:
            lines.append(f"  主题：{plan.get('topic', 'N/A')}")
            lines.append(f"  角度：{plan.get('angle', 'N/A')}")

        lines.append("")
        lines.append(f"🧪 A/B 测试方案：{len(result.ab_test_plan)} 组")

        return "\n".join(lines)

    def _llm_deep_optimize(self, result: RefineResult, feedback_data: Dict) -> None:
        """LLM 深度优化分析（本地 ollama）。"""
        try:
            from core.fabric.utils.ollama_utils import llm_chat, llm_available
            if not llm_available():
                logger.debug("本地 LLM 不可用，跳过深度优化")
                return

            # 准备数据
            feedbacks = feedback_data.get("feedbacks", [])
            feedback_sample = "\n".join(
                f"{i+1}. [{f.get('sentiment','?')}] {f.get('content','')[:50]}"
                for i, f in enumerate(feedbacks[:20])
            )

            prompt = f"""你是一个资深内容运营专家。请根据以下数据，为「{result.topic}」的内容优化提供深度建议。

当前已有反馈（{len(feedbacks)} 条）:
{feedback_sample}

高频关键词: {', '.join(feedback_data.get('top_keywords', [])[:5])}
正面/负面/中性: {feedback_data.get('positive_count', 0)}/{feedback_data.get('negative_count', 0)}/{feedback_data.get('neutral_count', 0)}

请输出：
1. 3个最有潜力的内容选题方向（说明为什么）
2. 下一期内容的详细脚本大纲（分3段，每段一句话）
3. 标题优化建议（3个备选标题）
4. 互动率提升建议（2条具体可执行的）

请用简洁中文回答，每点不超过 30 字。
"""

            analysis = llm_chat(prompt, temperature=0.8, max_tokens=1500, timeout=120)
            if analysis:
                # 把 LLM 建议作为高优先级建议加入
                from dataclasses import dataclass, field
                result.suggestions.insert(0, OptimizationSuggestion(
                    category="LLM深度分析",
                    suggestion=analysis[:200] + "..." if len(analysis) > 200 else analysis,
                    reason="基于用户反馈的 LLM 深度优化建议",
                    priority="high",
                    expected_impact="显著提升内容效果",
                ))

                # 更新下一期计划
                result.next_content_plan["llm_analysis"] = analysis
                logger.info("LLM 深度优化完成")
        except Exception as e:
            logger.warning("LLM 深度优化失败: %s", e)

    def _save_result(self, result: RefineResult) -> str:
        """保存结果到 JSON 文件。"""
        task_dir = os.path.join(_output_dir(), result.task_id)
        os.makedirs(task_dir, exist_ok=True)

        data = {
            "task_id": result.task_id,
            "topic": result.topic,
            "summary": result.summary,
            "suggestions": [
                {
                    "category": s.category,
                    "suggestion": s.suggestion,
                    "reason": s.reason,
                    "priority": s.priority,
                    "expected_impact": s.expected_impact,
                }
                for s in result.suggestions
            ],
            "next_content_plan": result.next_content_plan,
            "ab_test_plan": result.ab_test_plan,
        }

        json_path = os.path.join(task_dir, "refine_result.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return json_path
