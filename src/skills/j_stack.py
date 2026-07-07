"""
J Stack - 23 Expert Roles Skill Library.
Covers full lifecycle from requirements to deployment.
Each role injects a different expert mental model into AI.

23 Expert Roles by Phase:
  Requirement:  office-hours, product-manager, stakeholder-analyst
  Design:       design-thinking, architect, api-designer, database-architect, ux-designer
  Development:  developer, frontend-dev, backend-dev, prompt-engineer
  Quality:      tester, security-auditor, performance-engineer, compliance-officer
  Operations:   devops, sre, cost-optimizer, integration-specialist
  Retrospective: retro, tech-writer, knowledge-curator

Usage:
  registry.execute("j-stack", {"mode": "office-hours", "task": "..."})
  registry.execute("j-stack", {"mode": "multi", "roles": ["architect", "tester"], "task": "..."})
  registry.execute("j-stack", {"mode": "retro", "task": "..."})
"""

import logging
from datetime import datetime
from typing import Any, Dict, List
from .base import Skill, SkillMeta

logger = logging.getLogger(__name__)

ROLES = {
    "office-hours": {
        "title": "需求澄清师 (Office Hours)",
        "phase": "requirement",
        "description": "明确需求边界，澄清模糊点，避免方向性错误",
        "questions": [
            "用一句话描述核心需求是什么？",
            "这个问题为什么重要？不解决会怎样？",
            "期望的最终输出是什么？（格式/内容/质量）",
            "有哪些已知约束？（时间/资源/技术/合规）",
            "成功标准是什么？怎么判断已完成？",
        ],
        "output_format": "需求澄清文档 (含边界条件、验收标准)",
    },
    "product-manager": {
        "title": "产品经理",
        "phase": "requirement",
        "description": "从用户和市场角度审视需求，评估优先级和ROI",
        "questions": [
            "目标用户是谁？核心痛点是什么？",
            "竞品是怎么做的？差异化在哪里？",
            "MVP范围是什么？哪些可后续迭代？",
            "用户使用路径是怎样的？（画出来）",
            "有哪些数据指标可衡量成功？",
        ],
        "output_format": "产品需求文档(PRD)核心要素",
    },
    "stakeholder-analyst": {
        "title": "干系人分析师",
        "phase": "requirement",
        "description": "识别所有利益相关方及其诉求，平衡冲突需求",
        "questions": [
            "有哪些利益相关方？（列出所有）",
            "每方的核心关切是什么？",
            "哪些需求可能存在冲突？如何权衡？",
            "沟通计划是什么？谁需要什么信息？",
            "批准流程是怎样的？",
        ],
        "output_format": "干系人分析矩阵",
    },
    "design-thinking": {
        "title": "方案架构师",
        "phase": "design",
        "description": "系统化思考技术方案，评估架构选型和系统边界",
        "questions": [
            "识别组件：哪些模块/步骤组成？",
            "数据流：输入->处理->输出画出来",
            "技术选择：用现有工具还是需要新的？",
            "接口定义：组件间怎么通信(JSON/MCP/gRPC/REST)？",
            "失败点：哪里可能出错？怎么兜底？",
        ],
        "output_format": "技术方案设计文档",
    },
    "architect": {
        "title": "系统架构师",
        "phase": "design",
        "description": "从宏观架构视角审视系统设计，确保可扩展性和可维护性",
        "questions": [
            "系统边界在哪里？外部依赖有哪些？",
            "非功能需求：性能/安全/可用性/可扩展性？",
            "部署架构：单体还是微服务？容器化吗？",
            "数据存储：用什么数据库？读写分离？缓存？",
            "监控和可观测性：怎么知道系统健康？",
        ],
        "output_format": "架构决策记录(ADR)",
    },
    "api-designer": {
        "title": "API设计师",
        "phase": "design",
        "description": "设计清晰、一致、易用的API接口",
        "questions": [
            "资源模型：有哪些核心实体和关系？",
            "端点设计：GET/POST/PUT/DELETE语义正确？",
            "请求/响应格式：JSON Schema定义了吗？",
            "错误处理：统一的错误码和错误信息格式？",
            "版本策略：如何管理API版本兼容性？",
        ],
        "output_format": "OpenAPI/Swagger规范草案",
    },
    "database-architect": {
        "title": "数据库架构师",
        "phase": "design",
        "description": "设计高效、一致、可维护的数据模型",
        "questions": [
            "核心实体和属性有哪些？画ER图",
            "关系类型：一对一/一对多/多对多？",
            "索引策略：哪些字段需要索引？联合索引？",
            "数据量和增长预估：需要分库分表吗？",
            "数据一致性要求：强一致还是最终一致？",
        ],
        "output_format": "ER图 + 建表DDL",
    },
    "ux-designer": {
        "title": "UX设计师",
        "phase": "design",
        "description": "从用户体验角度审视设计，确保易用性和可访问性",
        "questions": [
            "用户流程：从进入到完成需要几步？能减吗？",
            "信息架构：导航是否清晰？用户能找到吗？",
            "反馈机制：每个操作都有明确反馈吗？",
            "错误恢复：用户犯错后如何优雅恢复？",
            "无障碍：色盲/键盘导航/屏幕阅读器支持？",
        ],
        "output_format": "UX审查报告 + 改进建议",
    },
    "developer": {
        "title": "全栈开发工程师",
        "phase": "development",
        "description": "关注代码质量、可读性和实现细节",
        "questions": [
            "核心算法逻辑是什么？时间复杂度？",
            "边界条件处理了吗？(空值/极端值/并发)",
            "错误处理完善吗？异常有分类处理吗？",
            "代码是否遵循SOLID原则？有重复代码吗？",
            "依赖管理：循环依赖？版本锁定？",
        ],
        "output_format": "代码实现 + 注意事项清单",
    },
    "frontend-dev": {
        "title": "前端开发专家",
        "phase": "development",
        "description": "专注前端实现，确保性能和可访问性",
        "questions": [
            "组件拆分：哪些可复用？状态管理？",
            "首屏加载性能：懒加载/代码分割？",
            "浏览器兼容性目标？polyfill需要吗？",
            "响应式设计：移动端和桌面端断点策略？",
            "前端安全：XSS/CSRF防护？敏感数据？",
        ],
        "output_format": "组件树 + 状态管理方案",
    },
    "backend-dev": {
        "title": "后端开发专家",
        "phase": "development",
        "description": "专注后端实现，确保可靠性和性能",
        "questions": [
            "并发处理：线程安全？连接池配置？",
            "事务管理：哪些需要事务？隔离级别？",
            "日志和追踪：关键路径有日志？链路追踪？",
            "限流和降级：高并发下如何保护？",
            "数据校验：输入验证完备？SQL注入防护？",
        ],
        "output_format": "后端实现方案 + 安全清单",
    },
    "prompt-engineer": {
        "title": "提示词工程师",
        "phase": "development",
        "description": "优化AI提示词，提高生成质量和一致性",
        "questions": [
            "角色定义清晰吗？(你是一个...)",
            "输出格式明确吗？有示例吗？",
            "约束条件足够具体吗？边界说明？",
            "有链式思维引导吗？(step-by-step)",
            "考虑幻觉防护了吗？(不确定时说不确定)",
        ],
        "output_format": "优化后的Prompt模板",
    },
    "tester": {
        "title": "测试工程师",
        "phase": "quality",
        "description": "系统化测试策略，覆盖正常/边界/异常",
        "questions": [
            "单元测试：核心逻辑覆盖率够吗？",
            "集成测试：关键接口上下游覆盖了吗？",
            "边界测试：最大值/最小值/null/空？",
            "异常测试：网络中断/超时/下游故障？",
            "回归测试：改动会影响哪些已有功能？",
        ],
        "output_format": "测试用例清单(按优先级排序)",
    },
    "security-auditor": {
        "title": "安全审计师",
        "phase": "quality",
        "description": "从安全视角审查代码和架构，防范常见漏洞",
        "questions": [
            "认证和授权：越权风险？Token管理安全？",
            "输入验证：SQL注入/XSS/命令注入防御？",
            "敏感数据：密钥/密码是否硬编码？加密？",
            "日志安全：记录敏感信息？访问控制？",
            "依赖安全：第三方库已知漏洞？",
        ],
        "output_format": "安全审计报告 + 风险等级",
    },
    "performance-engineer": {
        "title": "性能优化工程师",
        "phase": "quality",
        "description": "识别性能瓶颈，提出优化方案",
        "questions": [
            "热点路径在哪里？最频繁调用的函数？",
            "N+1查询问题？不必要的循环？",
            "缓存策略：哪些适合缓存？TTL设置？",
            "异步处理：哪些可异步化或批量处理？",
            "资源使用：内存/CPU/连接是否合理？",
        ],
        "output_format": "性能优化建议(含预期提升)",
    },
    "compliance-officer": {
        "title": "合规审查官",
        "phase": "quality",
        "description": "确保系统符合法规和标准要求",
        "questions": [
            "数据隐私：涉及个人信息？GDPR/个保法？",
            "数据跨境：存储和处理地理位置？",
            "许可证合规：开源库许可证兼容？",
            "行业特定要求：PCI-DSS/HIPAA等？",
            "审计日志：关键操作有不可篡改记录？",
        ],
        "output_format": "合规检查清单",
    },
    "devops": {
        "title": "DevOps工程师",
        "phase": "operations",
        "description": "关注部署、CI/CD和运维自动化",
        "questions": [
            "构建流程：Dockerfile/脚本可复现？",
            "CI/CD：提交后如何自动测试部署？",
            "环境管理：dev/staging/prod一致？",
            "回滚策略：部署失败如何快速回滚？",
            "密钥管理：安全注入？与代码分离？",
        ],
        "output_format": "CI/CD流水线设计 + Docker Compose",
    },
    "sre": {
        "title": "站点可靠性工程师(SRE)",
        "phase": "operations",
        "description": "确保系统高可用和可观测性",
        "questions": [
            "SLA/SLO：可用性目标？如何度量？",
            "监控告警：关键指标？阈值合理？",
            "容灾方案：单点故障在哪里？恢复时间？",
            "容量规划：资源使用率？何时扩容？",
            "On-Call：故障响应流程？Runbook？",
        ],
        "output_format": "可靠性评估报告 + SLO定义",
    },
    "cost-optimizer": {
        "title": "成本优化专家",
        "phase": "operations",
        "description": "在保障质量前提下降低运营成本",
        "questions": [
            "最大成本项？(计算/存储/网络/API)",
            "闲置资源可释放或降配？",
            "Spot/预留实例降低成本？",
            "API调用优化？(缓存/批处理/减调用)",
            "更经济的替代方案？(开源替代/自建)",
        ],
        "output_format": "成本优化方案(含预估节省)",
    },
    "integration-specialist": {
        "title": "集成专家",
        "phase": "operations",
        "description": "确保系统间顺畅集成，降低耦合风险",
        "questions": [
            "数据格式转换：需要ETL/数据清洗？",
            "协议适配：不同协议间如何转换？",
            "幂等性：重复请求是否安全？",
            "消息可靠性：丢失/重复如何处理？",
            "集成测试：如何模拟外部系统测试？",
        ],
        "output_format": "集成方案 + 异常场景处理矩阵",
    },
    "retro": {
        "title": "反思教练",
        "phase": "retrospective",
        "description": "引导深度反思，提炼经验教训",
        "questions": [
            "完成了哪些目标？哪些没完成？",
            "最大收获是什么？学到了什么？",
            "遇到了什么困难？怎么解决的？",
            "再重来一次会怎么做不同？",
            "有可提炼为技能的经验？(skill-creator)",
        ],
        "output_format": "回顾总结 + 可行动改进清单",
    },
    "tech-writer": {
        "title": "技术文档工程师",
        "phase": "retrospective",
        "description": "确保高质量文档，降低维护成本",
        "questions": [
            "README能让新人快速上手吗？",
            "API文档含请求/响应示例？",
            "架构决策有记录吗？(ADR)",
            "常见问题和排错指南完善吗？",
            "变更日志记录破坏性变更？",
        ],
        "output_format": "文档完善建议清单",
    },
    "knowledge-curator": {
        "title": "知识管理师",
        "phase": "retrospective",
        "description": "提炼和固化知识，避免重复踩坑",
        "questions": [
            "有什么可复用的代码/模式/流程？",
            "哪些经验值得沉淀？(skill-creator)",
            "哪些教训需记录？(更新禁区清单)",
            "知识库需更新吗？哪个分类？",
            "团队如何快速获取这些知识？",
        ],
        "output_format": "知识提炼 + 技能化建议",
    },
}

PER_PHASE_EXTRAS = {
    "requirement": "Next: use design-thinking for solution design",
    "design": "Next: use superpowers 5-gate pipeline for execution",
    "development": "Next: use tester + security-auditor for quality review",
    "quality": "Next: use devops for deployment planning",
    "operations": "Next: use retro for retrospective",
    "retrospective": "Tip: use skill-creator to solidify experience as skills",
}


class JStackSkill(Skill):
    """J Stack - 23 Expert Roles.

    Three core modes:
    1. office-hours    -> requirement clarification (3 roles)
    2. design-thinking -> solution design (5 roles)
    3. retro           -> retrospective + docs + knowledge (3 roles)
    Plus 14 individual expert roles for targeted review.

    Usage:
        # Three-phase mode
        registry.execute("j-stack", {"mode": "office-hours", "task": "..."})
        registry.execute("j-stack", {"mode": "design-thinking", "task": "..."})
        registry.execute("j-stack", {"mode": "retro", "task": "..."})

        # Multi-role review
        registry.execute("j-stack", {"mode": "multi",
            "roles": ["architect", "security-auditor", "tester"],
            "task": "..."})

        # Single expert role
        registry.execute("j-stack", {"mode": "developer", "task": "..."})
    """

    PHASE_GROUPS = {
        "office-hours": ["office-hours", "product-manager", "stakeholder-analyst"],
        "design-thinking": [
            "design-thinking", "architect", "api-designer",
            "database-architect", "ux-designer",
        ],
        "retro": ["retro", "tech-writer", "knowledge-curator"],
    }

    def __init__(self):
        meta = SkillMeta(
            name="j-stack",
            description=(
                "J Stack 23 Expert Roles: covers requirements->design->development"
                "->quality->operations->retrospective full lifecycle"
            ),
            version="2.0.0",
            tags=[
                "process", "clarification", "retrospective", "design",
                "architecture", "quality", "security", "devops",
                "23-roles", "expert-system",
            ],
            capabilities=[
                "requirements_clarification", "design_thinking",
                "architecture_review", "security_audit",
                "performance_review", "code_review", "testing_strategy",
                "devops_planning", "cost_optimization",
                "retrospective", "documentation", "knowledge_curation",
                "multi_role_review",
            ],
            category="autonomous-ai-agents",
        )
        super().__init__(meta)

    @property
    def available_roles(self):
        return list(ROLES.keys())

    @property
    def role_count(self):
        return len(ROLES)

    def list_roles_by_phase(self):
        phases = {}
        for rid, r in ROLES.items():
            phase = r["phase"]
            if phase not in phases:
                phases[phase] = []
            phases[phase].append({
                "id": rid, "title": r["title"],
                "description": r["description"],
            })
        return phases

    def execute(self, context):
        mode = context.get("mode", "").lower()
        task = context.get("task", context.get("message", ""))

        # list/roles mode does not need a task
        if mode in ("list", "roles", ""):
            return self._list_roles()

        if not task:
            return {"success": False, "error": "missing task or message field"}

        if mode == "multi":
            return self._execute_multi(task, context)
        if mode in self.PHASE_GROUPS:
            return self._execute_group(mode, task, context)
        if mode in ROLES:
            return self._execute_role(mode, task, context)
        if mode in ("list", "roles", ""):
            return self._list_roles()

        return {
            "success": False,
            "error": "Unknown mode '{}'. Use list/roles or office-hours/design-thinking/retro/multi.".format(mode),
        }

    def _execute_role(self, role_id, task, context):
        role = ROLES[role_id]
        answers = context.get("answers", [])

        if answers and len(answers) == len(role["questions"]):
            qa_pairs = [
                {"q": role["questions"][i], "a": answers[i]}
                for i in range(len(role["questions"]))
            ]
            return {
                "success": True, "mode": role_id,
                "role": role["title"], "phase": role["phase"],
                "task": task, "summary": {"qa_pairs": qa_pairs},
                "suggestion": PER_PHASE_EXTRAS.get(role["phase"], ""),
                "timestamp": datetime.now().isoformat(),
            }

        return {
            "success": True, "mode": role_id,
            "role": role["title"], "phase": role["phase"],
            "description": role["description"],
            "task": task, "questions": role["questions"],
            "questions_count": len(role["questions"]),
            "output_format": role["output_format"],
            "instruction": (
                "[Expert: {}] [{}]\nPlease answer {} questions:\n".format(
                    role["title"], role["phase"], len(role["questions"])) +
                "\n".join("  {}. {}".format(i+1, q)
                          for i, q in enumerate(role["questions"])) +
                "\n\nReturn: {{'mode': '{}', 'answers': [...]}}".format(role_id)
            ),
            "timestamp": datetime.now().isoformat(),
        }

    def _execute_group(self, group_id, task, context):
        role_ids = self.PHASE_GROUPS[group_id]
        roles_detail = [
            {"id": rid, "title": ROLES[rid]["title"],
             "description": ROLES[rid]["description"]}
            for rid in role_ids
        ]

        all_questions = []
        for rid in role_ids:
            for q in ROLES[rid]["questions"]:
                all_questions.append({
                    "role": rid, "role_title": ROLES[rid]["title"],
                    "question": q,
                })

        labels = {
            "office-hours": "Requirement Clarification",
            "design-thinking": "Solution Design",
            "retro": "Retrospective & Knowledge",
        }

        return {
            "success": True, "mode": group_id,
            "label": labels.get(group_id, group_id),
            "task": task, "roles": roles_detail,
            "roles_count": len(role_ids),
            "total_questions": len(all_questions),
            "questions_by_role": {
                rid: [{"question": q} for q in ROLES[rid]["questions"]]
                for rid in role_ids
            },
            "all_questions": all_questions,
            "instruction": (
                "[{}] {} expert perspectives\n".format(
                    labels.get(group_id, group_id), len(role_ids)) +
                "\n".join("  [{}]: {}".format(r["title"], r["description"])
                          for r in roles_detail) +
                "\n\nAnswer all questions, return answers_by_role dict"
            ),
            "timestamp": datetime.now().isoformat(),
        }

    def _execute_multi(self, task, context):
        requested_roles = context.get("roles", [])
        if not requested_roles:
            requested_roles = ["architect", "security-auditor", "tester"]

        valid_roles = [r for r in requested_roles if r in ROLES]
        invalid_roles = [r for r in requested_roles if r not in ROLES]

        if not valid_roles:
            return {
                "success": False,
                "error": "No valid roles. Available: {}...".format(
                    list(ROLES.keys())[:12]),
            }

        roles_detail = [
            {"id": rid, "title": ROLES[rid]["title"],
             "phase": ROLES[rid]["phase"],
             "questions": ROLES[rid]["questions"]}
            for rid in valid_roles
        ]

        return {
            "success": True, "mode": "multi",
            "task": task, "roles": valid_roles,
            "roles_detail": roles_detail,
            "invalid_roles": invalid_roles if invalid_roles else None,
            "total_roles": len(valid_roles),
            "total_questions": sum(len(r["questions"]) for r in roles_detail),
            "instruction": (
                "[Multi-Role Review] {} expert perspectives\n".format(len(valid_roles)) +
                "\n".join(
                    "  [{}] ({}): {}".format(
                        ROLES[rid]["title"], ROLES[rid]["phase"],
                        ROLES[rid]["description"])
                    for rid in valid_roles
                ) +
                "\n\nAnswer from each perspective, return answers_by_role dict"
            ),
            "timestamp": datetime.now().isoformat(),
        }

    def _list_roles(self):
        return {
            "success": True,
            "total_roles": len(ROLES),
            "roles": [
                {"id": rid, "title": r["title"], "phase": r["phase"],
                 "description": r["description"]}
                for rid, r in ROLES.items()
            ],
            "by_phase": self.list_roles_by_phase(),
            "phase_groups": {
                "office-hours": self.PHASE_GROUPS["office-hours"],
                "design-thinking": self.PHASE_GROUPS["design-thinking"],
                "retro": self.PHASE_GROUPS["retro"],
            },
            "usage": {
                "single": "j-stack | mode=<role_id> | task=...",
                "group": "j-stack | mode=office-hours|design-thinking|retro | task=...",
                "multi": "j-stack | mode=multi | roles=[architect,tester] | task=...",
            },
            "timestamp": datetime.now().isoformat(),
        }
