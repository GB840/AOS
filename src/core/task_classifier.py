"""
任务分级模块 - L1-L5 五级任务分级系统

核心职责:
1. 根据用户需求自动判断任务级别 (L1-L5)
2. 输出分级结果和处理通道
3. 为后续路由决策提供依据

分级规则:
L1 超级简单: 一句话问答、知识查询 → 直接本地模型回答
L2 简单任务: 单步骤、单工具 → 直接路由到对应角色
L3 普通任务: 3-5步、单角色主导 → 调用1个主要角色+辅助角色
L4 重型任务: 多步骤、多角色协作 → 完整元辩论+投票+编排
L5 复杂项目: 多模块、多阶段、跨领域 → 项目拆解+分层执行
"""

import logging
import json
import os
from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class TaskLevel(Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class TaskChannel(Enum):
    DIRECT = "直接对话"
    FAST = "快速通道"
    STANDARD = "标准通道"
    HEAVY = "重型通道"
    PROJECT = "项目通道"


@dataclass
class TaskClassification:
    level: TaskLevel
    reason: str
    estimated_steps: int
    channel: TaskChannel
    confidence: float = 0.0
    suggested_roles: List[str] = None
    is_complex: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "reason": self.reason,
            "estimated_steps": self.estimated_steps,
            "channel": self.channel.value,
            "confidence": self.confidence,
            "suggested_roles": self.suggested_roles or [],
            "is_complex": self.is_complex,
        }


TASK_CLASSIFICATION_PROMPT = """
任务分级规则:
1. 如果任务只需"回答问题/查询信息/单轮对话" → L1 (超级简单)
2. 如果任务只需"1-2步操作、1个工具、1个角色" → L2 (简单任务)
3. 如果任务需"3-5步工序、1个角色主导、少量辅助" → L3 (普通任务)
4. 如果任务需"多步骤、3+角色协作、有依赖关系" → L4 (重型任务)
5. 如果任务含"多个子项目、跨领域、需要阶段性交付" → L5 (复杂项目)

判断标准详解:
- L1: 无工具调用、无多步骤、纯知识问答、一句话能回答
- L2: 单一工具调用、单一角色、流程简单、无需协作
- L3: 需要一定工序但职责单一、1个主要角色+少量辅助角色
- L4: 需要多个专业角色协作、有明确的依赖关系和先后顺序
- L5: 包含多个独立子任务、跨领域协作、需要阶段性验收和交付

用户任务: {task}

输出格式 (JSON):
{{
  "level": "L1",
  "reason": "简要说明判断理由",
  "estimated_steps": 步骤数估算,
  "channel": "直接对话",
  "confidence": 0.0-1.0之间的置信度
}}

可选字段:
- "suggested_roles": ["角色1", "角色2"] — 如果能判断出需要的角色
- "is_complex": true/false — 是否为复杂任务(L4/L5)
"""


class TaskClassifier:
    """任务分级器 - 根据用户需求判断任务级别"""

    def __init__(self, brain=None):
        self.brain = brain
        self._cache = {}

    def classify(self, task: str, context: Optional[Dict[str, Any]] = None) -> TaskClassification:
        """对任务进行分级。

        优先 LLMRouter 直接调用（避免 brain.chat 递归），
        失败则回退 Hermes _route_l1，再失败则回退本地规则。
        设置 AOS_SEMANTIC_ROUTING=0 可跳过 LLM 直接走本地规则。"""
        if not task or not task.strip():
            return TaskClassification(
                level=TaskLevel.L1,
                reason="空任务",
                estimated_steps=0,
                channel=TaskChannel.DIRECT,
                confidence=1.0,
            )

        cached = self._check_cache(task)
        if cached:
            return cached

        # 语义分类（升华2 前提）：优先用 LLM 从 prompt 推断任务级别/通道(TaskType)；
        # 失败 / 低置信 / 未启用 时回落本地关键词规则。可用 AOS_SEMANTIC_ROUTING=0 关闭
        # （关闭后纯本地，省一次 LLM 调用，保留旧行为）。classify_with_llm 内部已自带
        # 低置信与异常回落，不会因 LLM 失败而中断路由。
        if os.getenv("AOS_SEMANTIC_ROUTING", "1") != "0" and self.brain is not None:
            classification = self.classify_with_llm(task)
        else:
            classification = self._local_classify(task)
        self._cache_result(task, classification)

        logger.info(f"任务分级完成: {classification.level.value} - {task[:50]}...")
        return classification

    def classify_with_llm(self, task: str) -> TaskClassification:
        """使用LLM进行更精确的分级。

        直接走 LLMRouter.chat() 避免经过 brain.chat 主循环（避免递归），
        也避免依赖 HermesAgent（可能未初始化）。LLMRouter 失败时回退 _route_l1，
        再失败则回退本地规则。
        """
        if not self.brain:
            return self._local_classify(task)

        prompt = TASK_CLASSIFICATION_PROMPT.format(task=task)
        response_text = ""

        # 路径 1: 直接走 LLMRouter（最可靠，不依赖 Hermes，不走 brain.chat 主循环）
        try:
            router = getattr(self.brain, "router", None)
            if router is not None:
                result = router.chat(
                    messages=[{"role": "user", "content": prompt}],
                    task_type=getattr(router, "TaskType", None),
                )
                if isinstance(result, dict) and result.get("success"):
                    response_text = result.get("content", "")
                    logger.debug("task_classifier: LLMRouter 路径成功")
        except Exception as e:
            logger.debug("task_classifier: LLMRouter 路径失败: %s", e)

        # 路径 2: 回退到 brain._route_l1（Hermes 路径，兼容旧行为）
        if not response_text:
            try:
                result = self.brain._route_l1(prompt, session_id="task_classification")
                response_text = result.get("response", "") if isinstance(result, dict) else ""
                logger.debug("task_classifier: _route_l1 回退路径成功")
            except Exception as e:
                logger.warning("LLM分级失败, 使用本地规则: %s", e)
                return self._local_classify(task)

        if not response_text:
            return self._local_classify(task)

        classification = self._parse_classification(response_text)
        if classification.confidence < 0.5:
            logger.debug("task_classifier: LLM 置信度低(%.2f), 回退本地规则", classification.confidence)
            return self._local_classify(task)
        return classification

    def _local_classify(self, task: str) -> TaskClassification:
        """本地规则分级(无LLM时的降级逻辑)"""
        task_lower = task.lower()

        simple_patterns = [
            "是什么", "什么是", "什么叫", "如何", "怎么", "为什么", "有哪些",
            "多少", "几", "谁", "何时", "哪里", "哪个", "能", "可以",
        ]
        tool_patterns = ["写代码", "生成", "创建", "设计", "分析", "整理", "翻译"]
        complex_patterns = ["系统", "架构", "项目", "平台", "完整", "全套", "方案"]
        multi_role_patterns = ["团队", "协作", "配合", "一起", "分工"]

        if any(p in task_lower for p in simple_patterns) and len(task) < 50:
            return TaskClassification(
                level=TaskLevel.L1,
                reason="简短问答类任务",
                estimated_steps=1,
                channel=TaskChannel.DIRECT,
                confidence=0.85,
            )

        if any(p in task_lower for p in tool_patterns) and not any(p in task_lower for p in complex_patterns):
            return TaskClassification(
                level=TaskLevel.L2,
                reason="单一工具/角色任务",
                estimated_steps=1,
                channel=TaskChannel.FAST,
                confidence=0.80,
            )

        if len(task) > 50 and any(p in task_lower for p in tool_patterns):
            return TaskClassification(
                level=TaskLevel.L3,
                reason="需要一定工序的任务",
                estimated_steps=3,
                channel=TaskChannel.STANDARD,
                confidence=0.75,
            )

        if any(p in task_lower for p in multi_role_patterns):
            return TaskClassification(
                level=TaskLevel.L4,
                reason="多角色协作任务",
                estimated_steps=5,
                channel=TaskChannel.HEAVY,
                confidence=0.85,
                is_complex=True,
            )

        if any(p in task_lower for p in complex_patterns):
            return TaskClassification(
                level=TaskLevel.L5,
                reason="复杂项目任务",
                estimated_steps=10,
                channel=TaskChannel.PROJECT,
                confidence=0.80,
                is_complex=True,
            )

        return TaskClassification(
            level=TaskLevel.L2,
            reason="默认分类为简单任务",
            estimated_steps=2,
            channel=TaskChannel.FAST,
            confidence=0.50,
        )

    def _parse_classification(self, response_text: str) -> TaskClassification:
        """解析LLM返回的分类结果"""
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response_text[start:end])
            else:
                data = json.loads(response_text)
        except (json.JSONDecodeError, ValueError):
            return self._local_classify(response_text)

        level_str = data.get("level", "L2").upper()
        try:
            level = TaskLevel(level_str)
        except ValueError:
            level = TaskLevel.L2

        channel_str = data.get("channel", "快速通道")
        channel_map = {
            "直接对话": TaskChannel.DIRECT,
            "快速通道": TaskChannel.FAST,
            "标准通道": TaskChannel.STANDARD,
            "重型通道": TaskChannel.HEAVY,
            "项目通道": TaskChannel.PROJECT,
        }
        channel = channel_map.get(channel_str, TaskChannel.FAST)

        return TaskClassification(
            level=level,
            reason=data.get("reason", "LLM分类"),
            estimated_steps=data.get("estimated_steps", 2),
            channel=channel,
            confidence=min(1.0, max(0.0, data.get("confidence", 0.7))),
            suggested_roles=data.get("suggested_roles", []),
            is_complex=level in (TaskLevel.L4, TaskLevel.L5),
        )

    def _check_cache(self, task: str) -> Optional[TaskClassification]:
        """检查缓存（进程内，按任务文本命中，避免重复 LLM 分类调用）"""
        return self._cache.get(task)

    def _cache_result(self, task: str, classification: TaskClassification):
        """缓存结果"""
        self._cache[task] = classification

    def get_channel_for_level(self, level: TaskLevel) -> TaskChannel:
        """根据级别获取处理通道"""
        channel_map = {
            TaskLevel.L1: TaskChannel.DIRECT,
            TaskLevel.L2: TaskChannel.FAST,
            TaskLevel.L3: TaskChannel.STANDARD,
            TaskLevel.L4: TaskChannel.HEAVY,
            TaskLevel.L5: TaskChannel.PROJECT,
        }
        return channel_map[level]

    def is_complex(self, level: TaskLevel) -> bool:
        """判断是否为复杂任务"""
        return level in (TaskLevel.L4, TaskLevel.L5)

    def get_channel_info(self, channel: TaskChannel) -> Dict[str, Any]:
        """获取通道信息"""
        info_map = {
            TaskChannel.DIRECT: {"name": "直通通道", "flow": "Hermes直接回复", "latency": "<2秒", "token_cost": "极低"},
            TaskChannel.FAST: {"name": "快速通道", "flow": "Hermes选1角色→直接执行", "latency": "5-10秒", "token_cost": "低"},
            TaskChannel.STANDARD: {"name": "标准通道", "flow": "选1主+1辅角色→轻量协商→执行", "latency": "15-30秒", "token_cost": "中"},
            TaskChannel.HEAVY: {"name": "重型通道", "flow": "元辩论→投票选3-5个→编排执行", "latency": "1-3分钟", "token_cost": "高但可控"},
            TaskChannel.PROJECT: {"name": "项目通道", "flow": "元辩论→拆分子任务→分层执行", "latency": "3-10分钟", "token_cost": "分阶段消耗"},
        }
        return info_map[channel]
