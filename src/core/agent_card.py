"""
AgentCARD 策略模块 - 成本-精度优化策略

核心职责:
1. 初稿阶段 → 使用本地小模型(Ollama/Llama.cpp)快速生成
2. 定稿阶段 → 使用付费大模型(GPT-4/Claude)进行润色和优化
3. 目标: 成本降低12倍, 精度保持

设计参考: AgentCARD - Adaptive Resource Allocation for Cost-Effective AI Deployment
- 根据任务阶段动态选择模型
- 初稿追求速度和成本效益
- 定稿追求质量和准确性
"""

import logging
import json
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class GenerationPhase(Enum):
    DRAFT = "draft"
    REVIEW = "review"
    POLISH = "polish"
    FINAL = "final"


class ModelTier(Enum):
    LOCAL = "local"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"


@dataclass
class ModelConfig:
    name: str
    tier: ModelTier
    provider: str
    input_cost_per_1k_tokens: float
    output_cost_per_1k_tokens: float
    max_tokens: int
    context_window: int
    capabilities: List[str] = field(default_factory=list)

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """估算成本"""
        input_cost = (input_tokens / 1000) * self.input_cost_per_1k_tokens
        output_cost = (output_tokens / 1000) * self.output_cost_per_1k_tokens
        return input_cost + output_cost


@dataclass
class GenerationResult:
    phase: GenerationPhase
    content: str
    model_used: str
    cost_usd: float
    tokens_used: Dict[str, int]
    quality_score: float = 0.0
    revised: bool = False


@dataclass
class CardStrategy:
    draft_model: ModelTier
    polish_model: ModelTier
    review_threshold: float = 0.7
    max_draft_attempts: int = 3
    enable_auto_polish: bool = True
    cost_saving_target: float = 0.9


class AgentCARD:
    """AgentCARD 成本-精度优化策略执行器"""

    MODEL_REGISTRY = {
        "ollama-llama3": ModelConfig(
            name="llama3",
            tier=ModelTier.LOCAL,
            provider="ollama",
            input_cost_per_1k_tokens=0.0,
            output_cost_per_1k_tokens=0.0,
            max_tokens=8192,
            context_window=8192,
            capabilities=["general", "code", "reasoning"],
        ),
        "ollama-mistral": ModelConfig(
            name="mistral",
            tier=ModelTier.LOCAL,
            provider="ollama",
            input_cost_per_1k_tokens=0.0,
            output_cost_per_1k_tokens=0.0,
            max_tokens=8192,
            context_window=8192,
            capabilities=["general", "code", "writing"],
        ),
        "llamacpp-phi3": ModelConfig(
            name="phi3",
            tier=ModelTier.SMALL,
            provider="llamacpp",
            input_cost_per_1k_tokens=0.0,
            output_cost_per_1k_tokens=0.0,
            max_tokens=4096,
            context_window=4096,
            capabilities=["general", "reasoning"],
        ),
        "openai-gpt-4o-mini": ModelConfig(
            name="gpt-4o-mini",
            tier=ModelTier.MEDIUM,
            provider="openai",
            input_cost_per_1k_tokens=0.0015,
            output_cost_per_1k_tokens=0.006,
            max_tokens=128000,
            context_window=128000,
            capabilities=["general", "code", "reasoning", "vision"],
        ),
        "openai-gpt-4o": ModelConfig(
            name="gpt-4o",
            tier=ModelTier.LARGE,
            provider="openai",
            input_cost_per_1k_tokens=0.005,
            output_cost_per_1k_tokens=0.015,
            max_tokens=128000,
            context_window=128000,
            capabilities=["general", "code", "reasoning", "vision", "complex"],
        ),
        "anthropic-claude-3-sonnet": ModelConfig(
            name="claude-3-sonnet",
            tier=ModelTier.LARGE,
            provider="anthropic",
            input_cost_per_1k_tokens=0.003,
            output_cost_per_1k_tokens=0.015,
            max_tokens=200000,
            context_window=200000,
            capabilities=["general", "code", "reasoning", "writing"],
        ),
        "anthropic-claude-3-opus": ModelConfig(
            name="claude-3-opus",
            tier=ModelTier.XLARGE,
            provider="anthropic",
            input_cost_per_1k_tokens=0.015,
            output_cost_per_1k_tokens=0.075,
            max_tokens=200000,
            context_window=200000,
            capabilities=["general", "code", "reasoning", "writing", "complex"],
        ),
    }

    def __init__(self, brain=None):
        self.brain = brain
        self._strategy_cache: Dict[str, CardStrategy] = {}
        self._generation_history: List[GenerationResult] = []

    def get_model_by_tier(self, tier: ModelTier) -> Optional[ModelConfig]:
        """根据模型等级获取模型配置"""
        for config in self.MODEL_REGISTRY.values():
            if config.tier == tier:
                return config
        return None

    def get_models_for_phase(self, phase: GenerationPhase) -> List[ModelConfig]:
        """获取指定阶段可用的模型"""
        if phase == GenerationPhase.DRAFT:
            return [m for m in self.MODEL_REGISTRY.values() if m.tier in (ModelTier.LOCAL, ModelTier.SMALL)]
        elif phase == GenerationPhase.REVIEW:
            return [m for m in self.MODEL_REGISTRY.values() if m.tier in (ModelTier.MEDIUM, ModelTier.LARGE)]
        elif phase == GenerationPhase.POLISH:
            return [m for m in self.MODEL_REGISTRY.values() if m.tier in (ModelTier.LARGE, ModelTier.XLARGE)]
        elif phase == GenerationPhase.FINAL:
            return [m for m in self.MODEL_REGISTRY.values() if m.tier == ModelTier.LARGE]
        return []

    def determine_strategy(self, task: str, task_level: str = "L3") -> CardStrategy:
        """确定AgentCARD策略"""
        task_lower = task.lower()

        if task_level in ("L4", "L5") or any(k in task_lower for k in ["系统", "架构", "复杂", "安全"]):
            return CardStrategy(
                draft_model=ModelTier.SMALL,
                polish_model=ModelTier.LARGE,
                review_threshold=0.8,
                max_draft_attempts=2,
            )
        elif task_level in ("L2", "L3") or any(k in task_lower for k in ["代码", "开发", "编程"]):
            return CardStrategy(
                draft_model=ModelTier.LOCAL,
                polish_model=ModelTier.MEDIUM,
                review_threshold=0.7,
                max_draft_attempts=3,
            )
        else:
            return CardStrategy(
                draft_model=ModelTier.LOCAL,
                polish_model=ModelTier.SMALL,
                review_threshold=0.6,
                max_draft_attempts=2,
            )

    def generate_draft(self, task: str, strategy: CardStrategy,
                       context: Optional[Dict[str, Any]] = None) -> GenerationResult:
        """生成初稿 - 使用小模型"""
        draft_model = self.get_model_by_tier(strategy.draft_model)
        if not draft_model:
            draft_model = self.MODEL_REGISTRY["ollama-llama3"]

        logger.info(f"AgentCARD 生成初稿: 使用 {draft_model.name}")

        try:
            result = self._call_model(draft_model, task, context)
            return GenerationResult(
                phase=GenerationPhase.DRAFT,
                content=result.get("content", ""),
                model_used=draft_model.name,
                cost_usd=result.get("cost", 0.0),
                tokens_used=result.get("tokens", {}),
                quality_score=0.0,
            )
        except Exception as e:
            logger.warning(f"初稿生成失败: {e}")
            return GenerationResult(
                phase=GenerationPhase.DRAFT,
                content="",
                model_used=draft_model.name,
                cost_usd=0.0,
                tokens_used={},
                quality_score=0.0,
            )

    def review_draft(self, draft: GenerationResult, task: str) -> float:
        """评审初稿 - 判断是否需要润色"""
        if not draft.content:
            return 0.0

        content_length = len(draft.content)
        has_code = any(tag in draft.content for tag in ["```", "def ", "function ", "class "])

        score = 0.5

        if content_length > 100:
            score += 0.2
        if content_length > 500:
            score += 0.1
        if has_code and "```python" in draft.content:
            score += 0.1

        if "错误" in draft.content or "无法" in draft.content:
            score -= 0.2

        return min(score, 1.0)

    def polish_draft(self, draft: GenerationResult, task: str,
                     strategy: CardStrategy) -> GenerationResult:
        """润色定稿 - 使用大模型"""
        polish_model = self.get_model_by_tier(strategy.polish_model)
        if not polish_model:
            polish_model = self.MODEL_REGISTRY["openai-gpt-4o-mini"]

        logger.info(f"AgentCARD 润色定稿: 使用 {polish_model.name}")

        polish_prompt = f"""
你是一位专业的技术评审和润色专家。请对以下初稿进行审核和优化：

任务要求: {task}

初稿内容:
{draft.content}

请完成以下工作：
1. 检查逻辑完整性和正确性
2. 优化代码质量（如果有代码）
3. 改善语言表达和格式
4. 补充缺失的部分
5. 确保符合最佳实践

输出优化后的完整内容。
"""

        try:
            result = self._call_model(polish_model, polish_prompt)
            return GenerationResult(
                phase=GenerationPhase.POLISH,
                content=result.get("content", ""),
                model_used=polish_model.name,
                cost_usd=result.get("cost", 0.0),
                tokens_used=result.get("tokens", {}),
                quality_score=0.9,
                revised=True,
            )
        except Exception as e:
            logger.warning(f"润色失败: {e}")
            return GenerationResult(
                phase=GenerationPhase.POLISH,
                content=draft.content,
                model_used=polish_model.name,
                cost_usd=0.0,
                tokens_used={},
                quality_score=0.7,
                revised=False,
            )

    def execute_full_pipeline(self, task: str, task_level: str = "L3",
                              context: Optional[Dict[str, Any]] = None) -> GenerationResult:
        """执行完整的AgentCARD流程"""
        strategy = self.determine_strategy(task, task_level)
        logger.info(f"AgentCARD 策略确定: 初稿={strategy.draft_model.value}, 定稿={strategy.polish_model.value}")

        draft = self.generate_draft(task, strategy, context)
        if not draft.content:
            logger.warning("初稿为空，跳过润色")
            return draft

        quality_score = self.review_draft(draft, task)
        logger.info(f"初稿评审分数: {quality_score:.2f}")

        if quality_score >= strategy.review_threshold:
            logger.info("初稿质量达标，直接使用")
            draft.quality_score = quality_score
            self._generation_history.append(draft)
            return draft

        if not strategy.enable_auto_polish:
            logger.info("自动润色未启用，返回初稿")
            draft.quality_score = quality_score
            self._generation_history.append(draft)
            return draft

        polished = self.polish_draft(draft, task, strategy)
        self._generation_history.append(polished)

        total_cost = draft.cost_usd + polished.cost_usd
        logger.info(f"AgentCARD 流程完成: 总成本=${total_cost:.4f}, 最终模型={polished.model_used}")

        return polished

    def _call_model(self, model: ModelConfig, prompt: str,
                    context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """调用指定模型"""
        estimated_input_tokens = len(prompt) // 4
        estimated_output_tokens = 1000

        if model.tier == ModelTier.LOCAL and self.brain:
            try:
                result = self.brain.hermes.chat(prompt)
                response = result if isinstance(result, str) else result.get("response", "")
                return {
                    "content": response,
                    "cost": 0.0,
                    "tokens": {"input": estimated_input_tokens, "output": len(response) // 4},
                }
            except Exception:
                pass

        return {
            "content": f"【模拟输出】使用{model.name}生成的内容\n\n基于任务: {prompt[:100]}...",
            "cost": model.estimate_cost(estimated_input_tokens, estimated_output_tokens),
            "tokens": {"input": estimated_input_tokens, "output": estimated_output_tokens},
        }

    def calculate_cost_saving(self, task_level: str) -> float:
        """计算成本节省比例"""
        strategy = self.determine_strategy("", task_level)
        draft_model = self.get_model_by_tier(strategy.draft_model)
        polish_model = self.get_model_by_tier(strategy.polish_model)

        if not draft_model or not polish_model:
            return 0.0

        all_large_cost = polish_model.estimate_cost(1000, 1000)
        card_cost = draft_model.estimate_cost(1000, 1000) * 0.7 + polish_model.estimate_cost(1000, 300) * 0.3

        if all_large_cost > 0:
            return (all_large_cost - card_cost) / all_large_cost
        return 0.0

    def get_strategy_stats(self) -> Dict[str, Any]:
        """获取策略统计信息"""
        stats = {
            "total_generations": len(self._generation_history),
            "draft_only": sum(1 for r in self._generation_history if r.phase == GenerationPhase.DRAFT and not r.revised),
            "polished": sum(1 for r in self._generation_history if r.revised),
            "total_cost": sum(r.cost_usd for r in self._generation_history),
            "average_quality": sum(r.quality_score for r in self._generation_history) / max(len(self._generation_history), 1),
        }
        return stats