"""
!!! DEPRECATED (2026-07-08) — 这是 AOS 自研的“OpenClaw 任务入口”，违反用户铁律
“四个能力必须用真实开源、不能自己写”。真实 OpenClaw 是 openclaws.io (MIT) 的自托管
网关，现已通过 src/core/fabric/adapters/openclaw_adapter.py 接入（调用真实 Gateway
http://127.0.0.1:18789）。本模块仅保留作兼容参考，不要再作为引擎实现使用。

OpenClaw 任务入口模块 - L1 任务入口层

核心职责:
1. 接单 - 接收用户原始需求
2. 清洗需求 - 标准化、去噪、补全缺失信息
3. 上报 Hermes - 将清洗后的需求传递给Hermes进行分级决策

设计参考: OpenClaw任务入口
- 作为系统的唯一入口
- 负责需求预处理和标准化
- 支持多渠道接入(文本、语音、文件)
"""

import logging
import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class InputChannel(Enum):
    TEXT = "text"
    VOICE = "voice"
    FILE = "file"
    API = "api"


class RequirementStatus(Enum):
    RECEIVED = "received"
    CLEANED = "cleaned"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass
class RawRequirement:
    task_id: str
    user_id: str
    input_text: str
    channel: InputChannel
    timestamp: str
    context: Dict[str, Any] = field(default_factory=dict)
    attachments: List[str] = field(default_factory=list)


@dataclass
class CleanedRequirement:
    task_id: str
    user_id: str
    original_text: str
    cleaned_text: str
    intent: str
    entities: Dict[str, Any] = field(default_factory=dict)
    requirements: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    missing_info: List[str] = field(default_factory=list)
    priority: str = "normal"
    estimated_complexity: float = 0.0
    status: RequirementStatus = RequirementStatus.CLEANED


@dataclass
class TaskTicket:
    ticket_id: str
    task_id: str
    user_id: str
    cleaned_requirement: CleanedRequirement
    classification: Optional[Dict[str, Any]] = None
    routing_channel: Optional[str] = None
    assigned_roles: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "cleaned_requirement": {
                "cleaned_text": self.cleaned_requirement.cleaned_text,
                "intent": self.cleaned_requirement.intent,
                "requirements": self.cleaned_requirement.requirements,
                "constraints": self.cleaned_requirement.constraints,
                "missing_info": self.cleaned_requirement.missing_info,
                "priority": self.cleaned_requirement.priority,
            },
            "classification": self.classification,
            "routing_channel": self.routing_channel,
            "assigned_roles": self.assigned_roles,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class OpenClaw:
    """OpenClaw 任务入口 - 接单、清洗需求、上报Hermes"""

    def __init__(self, brain=None):
        self.brain = brain
        self._tickets: Dict[str, TaskTicket] = {}
        self._pending_requirements: Dict[str, RawRequirement] = {}

    def receive_requirement(self, input_text: str, user_id: str = "default",
                            channel: InputChannel = InputChannel.TEXT,
                            context: Optional[Dict[str, Any]] = None,
                            attachments: Optional[List[str]] = None) -> RawRequirement:
        """接单 - 接收用户原始需求"""
        task_id = str(uuid.uuid4())[:8]
        requirement = RawRequirement(
            task_id=task_id,
            user_id=user_id,
            input_text=input_text,
            channel=channel,
            timestamp=datetime.now().isoformat(),
            context=context or {},
            attachments=attachments or [],
        )

        self._pending_requirements[task_id] = requirement
        logger.info(f"OpenClaw 接收到需求: task_id={task_id}, user={user_id}, length={len(input_text)}")

        return requirement

    def clean_requirement(self, requirement: RawRequirement) -> CleanedRequirement:
        """清洗需求 - 标准化、去噪、补全缺失信息"""
        cleaned_text = self._normalize_text(requirement.input_text)
        intent = self._detect_intent(cleaned_text)
        entities = self._extract_entities(cleaned_text)
        requirements = self._extract_requirements(cleaned_text)
        constraints = self._extract_constraints(cleaned_text)
        missing_info = self._identify_missing_info(cleaned_text, entities, requirements)
        priority = self._determine_priority(cleaned_text)
        complexity = self._estimate_complexity(cleaned_text, requirements)

        cleaned = CleanedRequirement(
            task_id=requirement.task_id,
            user_id=requirement.user_id,
            original_text=requirement.input_text,
            cleaned_text=cleaned_text,
            intent=intent,
            entities=entities,
            requirements=requirements,
            constraints=constraints,
            missing_info=missing_info,
            priority=priority,
            estimated_complexity=complexity,
            status=RequirementStatus.CLEANED,
        )

        logger.info(f"OpenClaw 需求清洗完成: task_id={requirement.task_id}, intent={intent}, requirements={len(requirements)}")
        return cleaned

    def _normalize_text(self, text: str) -> str:
        """文本标准化 - 去噪、统一格式"""
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[【】]", " ", text)
        text = re.sub(r"[<>《》]", " ", text)
        text = re.sub(r"\.{3,}", "。", text)
        text = text.replace("\n", " ")
        text = text.replace("\r", " ")
        return text.strip()

    def _detect_intent(self, text: str) -> str:
        """意图检测"""
        text_lower = text.lower()

        intent_patterns = [
            ("code", ["写代码", "编程", "开发", "代码", "bug", "修复", "api", "接口"]),
            ("design", ["设计", "架构", "界面", "UI", "UX", "原型"]),
            ("analysis", ["分析", "报告", "数据", "统计", "调研"]),
            ("writing", ["写", "文章", "文案", "文档", "报告"]),
            ("consulting", ["咨询", "建议", "方案", "策略", "规划"]),
            ("research", ["研究", "调研", "调查", "探索"]),
            ("search", ["搜索", "查找", "找", "查询"]),
            ("question", ["是什么", "什么是", "为什么", "如何", "怎么"]),
        ]

        for intent, patterns in intent_patterns:
            if any(p in text_lower for p in patterns):
                return intent

        return "general"

    def _extract_entities(self, text: str) -> Dict[str, Any]:
        """实体提取"""
        entities = {}

        domain_keywords = {
            "电商": ["电商", "商城", "购物", "订单", "商品"],
            "金融": ["金融", "银行", "支付", "贷款", "理财"],
            "医疗": ["医疗", "医院", "健康", "医生", "药品"],
            "教育": ["教育", "学习", "培训", "课程", "学校"],
            "社交": ["社交", "聊天", "社区", "交友"],
            "企业": ["企业", "公司", "办公", "管理"],
        }

        for domain, keywords in domain_keywords.items():
            if any(k in text for k in keywords):
                entities["domain"] = domain
                break

        tech_stack_keywords = {
            "python": ["python", "py"],
            "javascript": ["javascript", "js", "node"],
            "java": ["java", "spring", "maven"],
            "web": ["web", "前端", "后端", "网站"],
            "mobile": ["app", "手机", "移动端"],
            "ai": ["ai", "机器学习", "深度学习", "模型"],
        }

        for tech, keywords in tech_stack_keywords.items():
            if any(k.lower() in text.lower() for k in keywords):
                entities.setdefault("tech_stack", []).append(tech)

        deadline_patterns = [
            (r"(今天|今日)", "today"),
            (r"(明天|明日)", "tomorrow"),
            (r"(本周|这周)", "this_week"),
            (r"(下周)", "next_week"),
            (r"(\d+)天", "days"),
            (r"(\d+)小时", "hours"),
            (r"(\d+)分钟", "minutes"),
        ]

        for pattern, unit in deadline_patterns:
            match = re.search(pattern, text)
            if match:
                entities["deadline"] = {"match": match.group(), "unit": unit}
                break

        return entities

    def _extract_requirements(self, text: str) -> List[str]:
        """提取需求点"""
        sentences = re.split(r"[。！？；]", text)
        requirements = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 5:
                continue

            requirement_patterns = [
                r"(需要|必须|应该|要|得).*",
                r"(实现|开发|创建|设计|完成).*",
                r"(包含|包括|涵盖).*",
                r"(支持|提供|具备).*",
                r"(能够|可以|可).*",
            ]

            for pattern in requirement_patterns:
                match = re.search(pattern, sentence)
                if match:
                    requirements.append(sentence)
                    break

        if not requirements:
            requirements.append(text)

        return requirements

    def _extract_constraints(self, text: str) -> List[str]:
        """提取约束条件"""
        constraints = []
        constraint_keywords = [
            ("预算", ["预算", "价格", "费用"]),
            ("时间", ["时间", "期限", "deadline", "截止"]),
            ("技术", ["使用", "基于", "不使用", "限制"]),
            ("合规", ["合规", "安全", "保密", "隐私"]),
            ("性能", ["性能", "速度", "响应时间", "并发"]),
        ]

        for name, keywords in constraint_keywords:
            if any(k in text for k in keywords):
                constraints.append(name)

        return constraints

    def _identify_missing_info(self, text: str, entities: Dict[str, Any],
                               requirements: List[str]) -> List[str]:
        """识别缺失信息"""
        missing = []

        if "domain" not in entities:
            missing.append("业务领域")

        if len(requirements) > 1 and "deadline" not in entities:
            missing.append("时间要求")

        if any(r in text for r in ["系统", "平台", "项目"]) and "tech_stack" not in entities:
            missing.append("技术栈")

        if any(r in text for r in ["预算", "费用"]) and "预算" not in entities:
            missing.append("预算范围")

        return missing

    def _determine_priority(self, text: str) -> str:
        """确定优先级"""
        text_lower = text.lower()

        high_patterns = ["紧急", "立刻", "马上", "尽快", "现在", "立即"]
        medium_patterns = ["尽快", "这周", "本周", "需要"]

        if any(p in text_lower for p in high_patterns):
            return "high"
        elif any(p in text_lower for p in medium_patterns):
            return "medium"
        return "normal"

    def _estimate_complexity(self, text: str, requirements: List[str]) -> float:
        """估算复杂度"""
        complexity = 0.0

        complexity += min(len(requirements) * 0.1, 0.5)

        complex_keywords = ["系统", "架构", "项目", "平台", "完整", "全套"]
        if any(k in text for k in complex_keywords):
            complexity += 0.3

        entity_count = len([k for k in ["domain", "tech_stack", "deadline"] if k in text])
        complexity += entity_count * 0.05

        return min(complexity, 1.0)

    def validate_requirement(self, cleaned: CleanedRequirement) -> CleanedRequirement:
        """验证需求完整性"""
        if cleaned.missing_info:
            logger.warning(f"需求不完整: task_id={cleaned.task_id}, 缺失: {cleaned.missing_info}")
            cleaned.status = RequirementStatus.RECEIVED
        else:
            cleaned.status = RequirementStatus.VALIDATED
            logger.info(f"需求验证通过: task_id={cleaned.task_id}")

        return cleaned

    def escalate_to_hermes(self, cleaned: CleanedRequirement) -> TaskTicket:
        """上报Hermes - 创建工单并传递给Hermes进行分级决策"""
        ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d')}-{cleaned.task_id}"

        ticket = TaskTicket(
            ticket_id=ticket_id,
            task_id=cleaned.task_id,
            user_id=cleaned.user_id,
            cleaned_requirement=cleaned,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )

        self._tickets[ticket_id] = ticket

        if self.brain:
            classification = self.brain.get_task_classification(cleaned.cleaned_text)
            ticket.classification = classification
            ticket.routing_channel = classification.get("channel")
            ticket.updated_at = datetime.now().isoformat()
            logger.info(f"工单已上报Hermes: ticket_id={ticket_id}, channel={ticket.routing_channel}")

        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[TaskTicket]:
        """获取工单"""
        return self._tickets.get(ticket_id)

    def list_tickets(self, status: Optional[str] = None) -> List[TaskTicket]:
        """列出工单"""
        tickets = list(self._tickets.values())
        if status:
            tickets = [t for t in tickets if t.cleaned_requirement.status.value == status]
        return tickets

    def update_ticket(self, ticket_id: str, **kwargs) -> bool:
        """更新工单"""
        if ticket_id not in self._tickets:
            return False

        ticket = self._tickets[ticket_id]
        for key, value in kwargs.items():
            if hasattr(ticket, key):
                setattr(ticket, key, value)
        ticket.updated_at = datetime.now().isoformat()
        return True

    def process_request(self, input_text: str, user_id: str = "default",
                        channel: InputChannel = InputChannel.TEXT) -> TaskTicket:
        """完整流程: 接单 → 清洗 → 验证 → 上报"""
        raw = self.receive_requirement(input_text, user_id, channel)
        cleaned = self.clean_requirement(raw)
        validated = self.validate_requirement(cleaned)
        ticket = self.escalate_to_hermes(validated)

        logger.info(f"OpenClaw 完整流程完成: ticket_id={ticket.ticket_id}, level={ticket.classification.get('level') if ticket.classification else 'unknown'}")
        return ticket

    def get_missing_info_prompt(self, cleaned: CleanedRequirement) -> str:
        """生成询问缺失信息的提示"""
        if not cleaned.missing_info:
            return ""

        prompts = {
            "业务领域": "请问这个需求属于哪个业务领域？（如电商、金融、医疗等）",
            "时间要求": "请问有没有时间要求或截止日期？",
            "技术栈": "请问需要使用什么技术栈？",
            "预算范围": "请问预算范围是多少？",
        }

        questions = []
        for info in cleaned.missing_info:
            if info in prompts:
                questions.append(prompts[info])

        if questions:
            return "\n".join(questions) + "\n\n请补充以上信息，以便我更好地为您服务。"

        return ""