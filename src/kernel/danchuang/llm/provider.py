"""LLM 提供者抽象与默认实现。"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 响应封装。"""

    content: str
    model: str = "unknown"
    usage: Dict[str, Any] = None
    raw: Any = None


class LLMProvider(ABC):
    """LLM 提供者抽象基类。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        """调用 LLM。

        Args:
            messages: 消息列表，格式为 [{"role": "system/user/assistant", "content": "..."}]
            temperature: 温度
            max_tokens: 最大 token 数
            **kwargs: 额外参数

        Returns:
            LLMResponse
        """
        pass

    @abstractmethod
    def name(self) -> str:
        """返回提供者名称。"""
        pass


class MockLLM(LLMProvider):
    """模拟 LLM，用于无网络/无 API key 时的测试与演示。

    根据 system prompt 和 user prompt 中的关键词生成伪响应，
    后续可无缝替换为真实 LLM。
    """

    def __init__(self, model: str = "mock-llm"):
        self._model = model

    def name(self) -> str:
        return f"mock:{self._model}"

    def invoke(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2048,
        **kwargs,
    ) -> LLMResponse:
        system = ""
        user = ""
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            elif m.get("role") == "user":
                user = m.get("content", "")

        content = self._generate_response(system, user)
        return LLMResponse(
            content=content,
            model=self._model,
            usage={"prompt_tokens": len(system) + len(user), "completion_tokens": len(content)},
        )

    def _generate_response(self, system: str, user: str) -> str:
        text = (system + " " + user).lower()

        if any(k in text for k in ["眼镜", "硬件", "姿态", "矫正", "坐姿"]):
            return (
                "## 青少年护眼眼镜 MVP 方案\n\n"
                "1. 硬件选型：全志 XR806 主控 + GC0328 摄像头 + MPU6050 姿态传感器\n"
                "2. 算法：YOLOv8-nano 检测坐姿，MobileNet 做头部姿态估计\n"
                "3. 提醒方式：骨传导音频 + 震动马达，误报率目标 <5%\n"
                "4. BOM 成本：目标控制在 89 元以内\n"
                "5. 下阶段：打板 5 套样机，7 天内完成固件联调"
            )
        if any(k in text for k in ["市场", "调研", "竞品", "用户痛点"]):
            return (
                "## 市场调研结论\n\n"
                "- 竞品：小天才护眼仪（299元）、小米有品坐姿矫正器（159元）\n"
                "- 用户痛点：价格贵、误报多、孩子不愿意戴\n"
                "- 差异化：西南方言语音提醒 + 轻量化镜框 + 89元低价\n"
                "- 建议定价：129 元，毛利率 31%"
            )
        if any(k in text for k in ["营销", "抖音", "文案", "脚本", "海报"]):
            return (
                "## 抖音脚本：护眼眼镜\n\n"
                "【开场】孩子写作业又趴下了？\n"
                "【痛点】普通矫正器孩子嫌丑不爱戴\n"
                "【产品】单创OS 研发的西南方言 AI 护眼眼镜\n"
                "【卖点】轻至 28g、89 元、爷爷奶奶的口音提醒\n"
                "【CTA】评论区扣 1，领早鸟券"
            )
        if any(k in text for k in ["财务", "bom", "成本", "利润", "报表"]):
            return (
                "## 财务核算\n\n"
                "- 主控 XR806：12 元\n"
                "- 摄像头模组：8 元\n"
                "- 传感器：4 元\n"
                "- 镜框/结构件：18 元\n"
                "- 电池/PCB/其他：15 元\n"
                "- 加工组装：12 元\n"
                "- 单台 BOM：69 元，建议零售价 129 元，毛利 60 元/台"
            )

        return (
            "## 执行结果\n\n"
            "根据当前目标，我已完成了任务分析与初步方案设计。\n"
            "建议下一步进入具体实施阶段，并持续跟踪关键指标。"
        )


# 全局默认 LLM 实例（单例）
_default_llm: Optional[LLMProvider] = None


def get_default_provider() -> LLMProvider:
    """获取默认 LLM 提供者。"""
    global _default_llm
    if _default_llm is None:
        # 优先检查环境变量是否配置了真实模型
        import os
        provider_type = os.environ.get("DANCHUANG_LLM_PROVIDER", "mock").lower()

        if provider_type == "mock":
            _default_llm = MockLLM()
        else:
            # 后续扩展：local / openai / deepseek / dashscope
            _default_llm = MockLLM()
            logger.warning("LLM provider '%s' 尚未实现，回退到 MockLLM", provider_type)

    return _default_llm


def set_default_provider(provider: LLMProvider) -> None:
    """设置默认 LLM 提供者。"""
    global _default_llm
    _default_llm = provider
