"""
协商机制模块 - L3轻量协商 + L4终审交付

核心职责:
1. L3轻量协商 - 主角色与辅助角色之间的快速协作协商
2. L4终审交付 - 质量审核、打包、交付客户、存入记忆库

设计参考:
- L3: 1主+1辅角色 → 轻量协商 → 执行
- L4: 质量审核 → 打包 → 交付客户 → 存入记忆库
"""

import logging
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class NegotiationStatus(Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    DISAGREED = "disagreed"
    TIMEOUT = "timeout"


class ReviewStatus(Enum):
    PENDING = "pending"
    PASSED = "passed"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"


class DeliverableType(Enum):
    CODE = "code"
    DOCUMENT = "document"
    DATA = "data"
    MODEL = "model"
    REPORT = "report"
    OTHER = "other"


@dataclass
class NegotiationProposal:
    proposal_id: str
    role: str
    content: str
    requirements: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    estimated_time: str = ""
    priority: str = "normal"


@dataclass
class NegotiationResult:
    status: NegotiationStatus
    main_role: str
    support_role: str
    agreement: Dict[str, Any] = field(default_factory=dict)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""


@dataclass
class QualityCheck:
    check_id: str
    category: str
    description: str
    passed: bool = False
    score: float = 0.0
    feedback: str = ""


@dataclass
class Deliverable:
    type: DeliverableType
    name: str
    content: Any
    format: str = "text"
    version: str = "1.0.0"


@dataclass
class FinalDelivery:
    delivery_id: str
    task_id: str
    ticket_id: str
    task_description: str
    deliverables: List[Deliverable] = field(default_factory=list)
    quality_report: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    status: str = "completed"
    delivered_at: str = ""
    stored_in_memory: bool = False


class LightNegotiation:
    """L3轻量协商机制 - 主角色与辅助角色快速协作"""

    def __init__(self, skill_registry, brain=None):
        self.skill_registry = skill_registry
        self.brain = brain
        self._proposals: Dict[str, NegotiationProposal] = {}

    def propose(self, main_role: str, support_role: str, task: str) -> NegotiationProposal:
        """主角色提出协作方案"""
        proposal_id = f"PROP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6]}"

        main_skill = self._find_skill(main_role)
        support_skill = self._find_skill(support_role)

        proposal = NegotiationProposal(
            proposal_id=proposal_id,
            role=main_role,
            content=f"主角色[{main_role}]请求辅助角色[{support_role}]协作完成任务: {task}",
            requirements=self._extract_requirements(task),
            constraints=self._extract_constraints(task),
            dependencies=[support_role],
            estimated_time="15-30秒",
            priority=self._determine_priority(task),
        )

        self._proposals[proposal_id] = proposal
        logger.info(f"L3轻量协商: {main_role}提出方案 -> {support_role}, proposal_id={proposal_id}")

        return proposal

    def respond(self, proposal_id: str, support_role: str,
                accepted: bool, feedback: str = "") -> NegotiationResult:
        """辅助角色响应"""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return NegotiationResult(
                status=NegotiationStatus.DISAGREED,
                main_role=proposal.role if proposal else "unknown",
                support_role=support_role,
                notes="方案不存在",
            )

        if accepted:
            tasks = self._split_tasks(proposal, support_role)
            result = NegotiationResult(
                status=NegotiationStatus.AGREED,
                main_role=proposal.role,
                support_role=support_role,
                agreement={
                    "proposal_id": proposal_id,
                    "accepted": True,
                    "feedback": feedback,
                },
                tasks=tasks,
                notes="双方达成一致",
            )
            logger.info(f"L3轻量协商: {support_role}接受方案, 任务已拆分")
        else:
            result = NegotiationResult(
                status=NegotiationStatus.DISAGREED,
                main_role=proposal.role,
                support_role=support_role,
                notes=f"辅助角色拒绝: {feedback}",
            )
            logger.warning(f"L3轻量协商: {support_role}拒绝方案")

        return result

    def _find_skill(self, role_name: str):
        """查找角色技能"""
        skills = self.skill_registry.list_all()
        return next((s for s in skills if s.get("name") == role_name), None)

    def _extract_requirements(self, task: str) -> List[str]:
        """提取需求"""
        import re
        sentences = re.split(r"[。！？；]", task)
        requirements = []
        for sentence in sentences:
            sentence = sentence.strip()
            if any(p in sentence for p in ["需要", "必须", "应该", "实现", "开发"]):
                requirements.append(sentence)
        return requirements[:5]

    def _extract_constraints(self, task: str) -> List[str]:
        """提取约束"""
        constraints = []
        constraint_keywords = ["时间", "预算", "技术", "安全", "性能"]
        for keyword in constraint_keywords:
            if keyword in task:
                constraints.append(keyword)
        return constraints

    def _determine_priority(self, task: str) -> str:
        """确定优先级"""
        if any(p in task for p in ["紧急", "立刻", "马上"]):
            return "high"
        return "normal"

    def _split_tasks(self, proposal: NegotiationProposal, support_role: str) -> List[Dict[str, Any]]:
        """拆分工单"""
        tasks = []

        tasks.append({
            "task_id": f"TASK-MAIN-{str(uuid.uuid4())[:6]}",
            "role": proposal.role,
            "description": "执行主任务核心逻辑",
            "input": proposal.content,
            "output": "核心产出",
            "dependencies": [],
            "priority": proposal.priority,
        })

        tasks.append({
            "task_id": f"TASK-SUPPORT-{str(uuid.uuid4())[:6]}",
            "role": support_role,
            "description": "提供辅助支持",
            "input": "主角色产出",
            "output": "辅助产出",
            "dependencies": [tasks[0]["task_id"]],
            "priority": "normal",
        })

        return tasks

    def run_negotiation(self, main_role: str, support_role: str, task: str) -> NegotiationResult:
        """运行完整协商流程"""
        proposal = self.propose(main_role, support_role, task)
        result = self.respond(proposal.proposal_id, support_role, accepted=True)
        return result


class FinalDeliverySystem:
    """L4终审交付系统 - 质量审核、打包、交付、存入记忆库"""

    def __init__(self, task_fingerprint=None, memory_manager=None):
        self.task_fingerprint = task_fingerprint
        self.memory_manager = memory_manager
        self._deliveries: Dict[str, FinalDelivery] = {}
        self._quality_checks: Dict[str, List[QualityCheck]] = {}

    def run_quality_checks(self, task_description: str, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """执行质量审核"""
        checks = [
            QualityCheck(
                check_id="QC-001",
                category="完整性",
                description="检查是否完成所有需求点",
            ),
            QualityCheck(
                check_id="QC-002",
                category="正确性",
                description="检查逻辑和代码是否正确",
            ),
            QualityCheck(
                check_id="QC-003",
                category="格式规范",
                description="检查输出格式是否符合规范",
            ),
            QualityCheck(
                check_id="QC-004",
                category="安全性",
                description="检查是否存在安全隐患",
            ),
            QualityCheck(
                check_id="QC-005",
                category="性能",
                description="检查是否存在性能问题",
            ),
        ]

        for check in checks:
            check.passed, check.score, check.feedback = self._evaluate_check(check, task_description, outputs)

        self._quality_checks[task_description[:50]] = checks

        passed_count = sum(1 for c in checks if c.passed)
        overall_score = sum(c.score for c in checks) / len(checks)

        report = {
            "total_checks": len(checks),
            "passed": passed_count,
            "failed": len(checks) - passed_count,
            "overall_score": overall_score,
            "status": "passed" if passed_count >= len(checks) * 0.8 else ("needs_revision" if passed_count >= len(checks) * 0.5 else "rejected"),
            "details": [c.to_dict() if hasattr(c, 'to_dict') else {
                "check_id": c.check_id,
                "category": c.category,
                "description": c.description,
                "passed": c.passed,
                "score": c.score,
                "feedback": c.feedback,
            } for c in checks],
        }

        logger.info(f"L4质量审核完成: 总分={overall_score:.2f}, 状态={report['status']}")
        return report

    def _evaluate_check(self, check: QualityCheck, task: str, outputs: Dict[str, Any]) -> tuple:
        """评估单项检查"""
        content = str(outputs) if isinstance(outputs, dict) else outputs

        if check.category == "完整性":
            has_content = len(str(content)) > 100
            score = 0.9 if has_content else 0.3
            return has_content, score, "内容充足" if has_content else "内容过少"

        elif check.category == "正确性":
            has_code = "```" in str(content)
            has_error = any(e in str(content).lower() for e in ["error", "错误", "fail"])
            score = 0.8 if has_code and not has_error else 0.5
            return not has_error, score, "无明显错误" if not has_error else "包含错误信息"

        elif check.category == "格式规范":
            has_structure = any(s in str(content) for s in ["##", "###", "- ", "* ", "```"])
            score = 0.8 if has_structure else 0.4
            return has_structure, score, "格式规范" if has_structure else "缺少结构化格式"

        elif check.category == "安全性":
            has_sensitive = any(s in str(content).lower() for s in ["password", "secret", "token", "key"])
            score = 0.9 if not has_sensitive else 0.2
            return not has_sensitive, score, "无敏感信息" if not has_sensitive else "可能包含敏感信息"

        elif check.category == "性能":
            length = len(str(content))
            is_reasonable = length < 10000
            score = 0.8 if is_reasonable else 0.5
            return is_reasonable, score, "内容长度合理" if is_reasonable else "内容过长"

        return True, 0.7, "检查通过"

    def package_deliverables(self, task_description: str, outputs: Dict[str, Any],
                             quality_report: Dict[str, Any]) -> List[Deliverable]:
        """打包交付物"""
        deliverables = []

        for key, value in outputs.items():
            if isinstance(value, str):
                if "```python" in value or "```code" in value:
                    deliverable_type = DeliverableType.CODE
                    fmt = "python"
                elif "##" in value or "###" in value:
                    deliverable_type = DeliverableType.DOCUMENT
                    fmt = "markdown"
                else:
                    deliverable_type = DeliverableType.REPORT
                    fmt = "text"
            elif isinstance(value, dict):
                deliverable_type = DeliverableType.DATA
                fmt = "json"
            else:
                deliverable_type = DeliverableType.OTHER
                fmt = "text"

            deliverables.append(Deliverable(
                type=deliverable_type,
                name=key,
                content=value,
                format=fmt,
                version="1.0.0",
            ))

        logger.info(f"L4打包完成: {len(deliverables)}个交付物")
        return deliverables

    def deliver_to_customer(self, task_id: str, ticket_id: str, task_description: str,
                            deliverables: List[Deliverable], quality_report: Dict[str, Any]) -> FinalDelivery:
        """交付给客户"""
        delivery_id = f"DLV-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6]}"

        summary = self._generate_delivery_summary(task_description, deliverables, quality_report)

        delivery = FinalDelivery(
            delivery_id=delivery_id,
            task_id=task_id,
            ticket_id=ticket_id,
            task_description=task_description,
            deliverables=deliverables,
            quality_report=quality_report,
            summary=summary,
            status=quality_report.get("status", "completed"),
            delivered_at=datetime.now().isoformat(),
            stored_in_memory=False,
        )

        self._deliveries[delivery_id] = delivery
        logger.info(f"L4交付完成: delivery_id={delivery_id}, 状态={delivery.status}")

        return delivery

    def _generate_delivery_summary(self, task: str, deliverables: List[Deliverable],
                                   quality_report: Dict[str, Any]) -> str:
        """生成交付摘要"""
        summary = f"任务完成: {task[:50]}...\n\n"
        summary += f"交付物 ({len(deliverables)}个):\n"
        for d in deliverables:
            summary += f"  - [{d.type.value}] {d.name}\n"
        summary += f"\n质量评分: {quality_report.get('overall_score', 0):.2f}\n"
        summary += f"审核状态: {quality_report.get('status', 'unknown')}"
        return summary

    def store_in_memory(self, delivery: FinalDelivery, level: str,
                        role_whitelist: List[str], orchestration_spec: Dict[str, Any] = None,
                        model_strategy: Dict[str, str] = None):
        """存入记忆库"""
        if self.task_fingerprint:
            self.task_fingerprint.store_template(
                task=delivery.task_description,
                level=level,
                role_whitelist=role_whitelist,
                orchestration_spec=orchestration_spec or {},
                model_strategy=model_strategy or {},
            )
            delivery.stored_in_memory = True
            logger.info(f"L4记忆沉淀完成: task_id={delivery.task_id}")

    def execute_full_delivery(self, task_id: str, ticket_id: str, task_description: str,
                              outputs: Dict[str, Any], level: str = "L4",
                              role_whitelist: Optional[List[str]] = None,
                              orchestration_spec: Optional[Dict[str, Any]] = None,
                              model_strategy: Optional[Dict[str, str]] = None) -> FinalDelivery:
        """执行完整交付流程"""
        quality_report = self.run_quality_checks(task_description, outputs)
        deliverables = self.package_deliverables(task_description, outputs, quality_report)
        delivery = self.deliver_to_customer(task_id, ticket_id, task_description, deliverables, quality_report)
        self.store_in_memory(delivery, level, role_whitelist or [], orchestration_spec, model_strategy)

        logger.info(f"L4完整交付流程完成: task_id={task_id}, delivery_id={delivery.delivery_id}")
        return delivery

    def get_delivery(self, delivery_id: str) -> Optional[FinalDelivery]:
        """获取交付记录"""
        return self._deliveries.get(delivery_id)

    def list_deliveries(self, status: Optional[str] = None) -> List[FinalDelivery]:
        """列出交付记录"""
        deliveries = list(self._deliveries.values())
        if status:
            deliveries = [d for d in deliveries if d.status == status]
        return deliveries