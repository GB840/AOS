"""
元辩论模块 - 动态角色分配与同行评审投票系统

核心职责:
1. 候选Agent"自我推销" — 每个角色阐述为何适合当前任务
2. 同行评审 — 角色之间互相评价
3. 投票选出3-5个最合适的角色
4. 输出角色白名单 + 成本预算 + 模型分配策略

设计参考: AgentCARD 成本-精度优化策略
- 初稿 → 本地Ollama小模型
- 定稿润色 → 付费大模型
- 目标: 成本降低12倍, 精度保持
"""

import logging
import json
from typing import Dict, List, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ModelTier(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RoleCandidate:
    name: str
    category: str
    description: str
    capabilities: List[str]
    pitch: str = ""
    score: float = 0.0
    votes: int = 0
    model_tier: ModelTier = ModelTier.MEDIUM
    estimated_tokens: int = 0


@dataclass
class DebateResult:
    selected_roles: List[RoleCandidate]
    role_whitelist: List[str]
    cost_budget: Dict[str, Any]
    model_strategy: Dict[str, ModelTier]
    debate_summary: str
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_roles": [{"name": r.name, "category": r.category, "score": r.score, "votes": r.votes} for r in self.selected_roles],
            "role_whitelist": self.role_whitelist,
            "cost_budget": self.cost_budget,
            "model_strategy": {k: v.value for k, v in self.model_strategy.items()},
            "debate_summary": self.debate_summary,
            "confidence": self.confidence,
        }


SELF_PITCH_PROMPT = """
你是【{role_name}】，请针对以下任务进行"自我推销"：

任务描述: {task}

你的身份描述: {role_description}

你的核心能力: {capabilities}

请用50-100字说明：
1. 你为什么适合这个任务？
2. 你能为任务带来什么独特价值？
3. 你需要什么支持或配合？

输出要求: 直接给出推销内容，不要多余解释。
"""


PEER_REVIEW_PROMPT = """
你是【{reviewer_name}】，请对以下候选人进行同行评审：

任务描述: {task}

候选人: {candidate_name}
候选人描述: {candidate_description}
候选人自我推销: {candidate_pitch}

请从以下维度进行评价（0-10分）：
1. 专业匹配度 — 该角色的专业能力与任务需求的匹配程度
2. 协作兼容性 — 与其他角色协作的能力
3. 任务必要性 — 该角色是否为任务必需

评分格式（JSON）：
{{
  "candidate": "{candidate_name}",
  "reviewer": "{reviewer_name}",
  "scores": {{
    "professional_match": 0-10,
    "collaboration_compatibility": 0-10,
    "task_necessity": 0-10
  }},
  "comment": "简要评价"
}}
"""


class MetaDebate:
    """元辩论系统 — 动态角色分配+同行评审+投票"""

    def __init__(self, skill_registry, brain=None):
        self.skill_registry = skill_registry
        self.brain = brain
        self._candidates = []

    def prepare_candidates(self, task: str, max_candidates: int = 10) -> List[RoleCandidate]:
        """准备候选角色列表"""
        all_skills = self.skill_registry.list_all()
        filtered = []

        for skill in all_skills:
            if skill.get("category") == "agency_roles":
                candidate = RoleCandidate(
                    name=skill["name"],
                    category=skill.get("category", "general"),
                    description=skill.get("description", ""),
                    capabilities=skill.get("capabilities", []),
                )
                filtered.append(candidate)

        if not filtered:
            for skill in all_skills:
                candidate = RoleCandidate(
                    name=skill["name"],
                    category=skill.get("category", "general"),
                    description=skill.get("description", ""),
                    capabilities=skill.get("capabilities", []),
                )
                filtered.append(candidate)

        self._candidates = filtered[:max_candidates]
        logger.info(f"准备了 {len(self._candidates)} 个候选角色")
        return self._candidates

    def run_self_pitch(self, task: str) -> List[RoleCandidate]:
        """执行自我推销阶段 - 使用本地规则避免递归调用"""
        task_lower = task.lower()
        
        for candidate in self._candidates:
            match_score = self._calculate_match_score(candidate, task_lower)
            candidate.score = match_score
            candidate.pitch = f"我是{candidate.name}，擅长{candidate.description[:50]}，匹配度: {match_score:.2f}"
            logger.info(f"自我推销完成: {candidate.name}")

        return self._candidates

    def _calculate_match_score(self, candidate, task_lower):
        """计算角色与任务的匹配度"""
        score = 0.0
        
        keywords = []
        if "开发" in task_lower or "代码" in task_lower or "api" in task_lower:
            keywords.extend(["开发", "代码", "编程", "engineer", "developer"])
        if "设计" in task_lower or "架构" in task_lower:
            keywords.extend(["设计", "架构", "design", "architecture"])
        if "营销" in task_lower or "推广" in task_lower:
            keywords.extend(["营销", "推广", "marketing", "sales"])
        if "数据" in task_lower or "分析" in task_lower:
            keywords.extend(["数据", "分析", "data", "analysis"])
        
        name_lower = candidate.name.lower()
        desc_lower = candidate.description.lower()
        
        for kw in keywords:
            if kw in name_lower:
                score += 0.3
            if kw in desc_lower:
                score += 0.2
        
        if candidate.capabilities:
            for cap in candidate.capabilities:
                if any(kw in cap.lower() for kw in keywords):
                    score += 0.1
        
        score += 0.2
        
        return min(score, 1.0)

    def run_peer_review(self, task: str, top_n: int = 6) -> List[RoleCandidate]:
        """执行同行评审阶段 - 使用本地规则避免递归调用"""
        candidates_to_review = sorted(self._candidates, key=lambda x: x.score, reverse=True)[:top_n]

        for reviewer in candidates_to_review:
            for candidate in candidates_to_review:
                if reviewer.name == candidate.name:
                    continue
                
                try:
                    if reviewer.score > 0.5 and candidate.score > 0.3:
                        candidate.score += 0.1
                        candidate.votes += 1
                except Exception as e:
                    logger.warning(f"同行评审失败 {reviewer.name} -> {candidate.name}: {e}")

        return candidates_to_review

    def _parse_review(self, response: str) -> Dict[str, float]:
        """解析评审结果"""
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                data = json.loads(response)
            scores = data.get("scores", {})
            return {k: float(v) for k, v in scores.items()}
        except (json.JSONDecodeError, ValueError):
            return {}

    def vote(self, top_k: int = 5) -> List[RoleCandidate]:
        """投票选出最佳角色"""
        sorted_candidates = sorted(self._candidates, key=lambda x: (x.score, x.votes), reverse=True)
        return sorted_candidates[:top_k]

    def assign_models(self, selected: List[RoleCandidate]) -> Dict[str, ModelTier]:
        """为角色分配模型等级"""
        strategy = {}
        for role in selected:
            complex_categories = ["engineering", "security", "legal", "finance"]
            creative_categories = ["design", "marketing", "writing", "content"]

            if role.category in complex_categories:
                strategy[role.name] = ModelTier.HIGH
            elif role.category in creative_categories:
                strategy[role.name] = ModelTier.MEDIUM
            else:
                strategy[role.name] = ModelTier.LOW

        return strategy

    def calculate_budget(self, selected: List[RoleCandidate], model_strategy: Dict[str, ModelTier]) -> Dict[str, Any]:
        """计算成本预算"""
        token_rates = {
            ModelTier.LOW: 0.001,
            ModelTier.MEDIUM: 0.005,
            ModelTier.HIGH: 0.02,
        }

        estimated_tokens = {role.name: 5000 for role in selected}
        estimated_cost = {}

        total_cost = 0.0
        total_tokens = 0

        for role in selected:
            tier = model_strategy[role.name]
            tokens = estimated_tokens[role.name]
            cost = tokens * token_rates[tier] / 1000
            estimated_cost[role.name] = {
                "model_tier": tier.value,
                "estimated_tokens": tokens,
                "estimated_cost_usd": round(cost, 4),
            }
            total_cost += cost
            total_tokens += tokens

        return {
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "by_role": estimated_cost,
            "savings_estimate": round(total_cost * 0.9, 4),
        }

    def run_full_debate(self, task: str, max_candidates: int = 10, top_k: int = 5) -> DebateResult:
        """执行完整的元辩论流程"""
        logger.info(f"开始元辩论: {task[:50]}...")

        self.prepare_candidates(task, max_candidates)
        self.run_self_pitch(task)
        self.run_peer_review(task)

        selected = self.vote(top_k)
        role_whitelist = [r.name for r in selected]
        model_strategy = self.assign_models(selected)
        cost_budget = self.calculate_budget(selected, model_strategy)

        summary = f"元辩论完成: 从{len(self._candidates)}个候选中选出{len(selected)}个角色"
        summary += f"\n选中角色: {', '.join([r.name for r in selected])}"
        summary += f"\n预计成本: ${cost_budget['total_cost_usd']}"

        logger.info(summary)

        return DebateResult(
            selected_roles=selected,
            role_whitelist=role_whitelist,
            cost_budget=cost_budget,
            model_strategy=model_strategy,
            debate_summary=summary,
            confidence=min(1.0, len(selected) / 5),
        )
