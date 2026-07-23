"""单创OS（DanchuangOS）总入口 v2.0 — 炼化融合版。

整合六大核心能力，为单人创业者提供完整的 AI 一人公司操作系统：

1. OPC 数字组织内核（5大岗位 + 147+细分专业角色）
   来源：agency-agents-zh（The Agency 中文翻译版）

2. 创业目标调度引擎（目标拆解 → 任务分配 → 进度监控 → 复盘迭代）
   融合：GoalDecomposer + TaskScheduler

3. Crew 编排引擎（角色+任务+流程协作）
   借鉴：CrewAI 的角色扮演多智能体协作模式

4. Playbook 工作流模板库 + 状态检查点
   借鉴：The Agency playbooks + LangGraph checkpoint
   内置 5+ 行业剧本：创业MVP、硬件开发、内容营销、电商开店、市场调研

5. 多租户 SaaS 隔离层（数据隔离 + 套餐配额 + 使用统计）
   支持：免费/标准版/专业版/企业版 四档套餐

6. 平台管理员 API（全局管控 + 数据看板 + 系统监控）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .opc.roles import OPCRole, OPCAgentRole, create_agent, get_all_roles
from .opc.agency_registry import AgencyRegistry, get_agency_registry
from .engine.startup_engine import StartupEngine
from .engine.crew_orchestrator import (
    CrewOrchestrator,
    CrewTask,
    CrewAgent,
    ProcessType,
    TaskExecutor,
)
from .engine.playbook_library import (
    PlaybookLibrary,
    WorkflowStateManager,
    WorkflowStatus,
)
from .tenant.tenant_manager import TenantManager
from .tenant.isolation import TenantDataIsolation
from .tenant.saas_manager import UsageManager, AdminManager, UsageMetric, PlanTier
from .templates import get_template, list_templates, IndustryType, IndustryTemplate

logger = logging.getLogger(__name__)


@dataclass
class DanchuangOSStatus:
    """系统状态总览。"""

    tenant_count: int = 0
    active_tenants: int = 0
    total_goals: int = 0
    total_tasks: int = 0
    total_agents: int = 0
    total_playbooks: int = 0
    supported_industries: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tenant_count": self.tenant_count,
            "active_tenants": self.active_tenants,
            "total_goals": self.total_goals,
            "total_tasks": self.total_tasks,
            "total_agents": self.total_agents,
            "total_playbooks": self.total_playbooks,
            "supported_industries": self.supported_industries or [],
        }


class DanchuangOS:
    """单创OS：AI一人公司操作系统 v2.0（炼化融合版）。

    融合六大核心能力：
    - OPC 数字组织内核（5大岗位 + 147+专业角色）
    - 创业目标调度引擎
    - Crew 协作编排（CrewAI式）
    - Playbook 工作流模板库 + 状态检查点
    - 多租户 SaaS 隔离层
    - 平台管理员 API

    技术融合来源：
    - The Agency：147+专业角色库 + playbooks
    - CrewAI：角色+任务+流程的协作编排
    - LangGraph：状态检查点 + 时间旅行调试
    - AOS：FabricHub + DeerFlow + Hermes 基础设施
    """

    def __init__(self, data_dir: str = None):
        from pathlib import Path
        if data_dir is None:
            data_dir = str(Path(__file__).resolve().parents[3] / "data" / "danchuang")

        self._data_dir = data_dir

        self._tenant_manager = TenantManager(db_path=f"{data_dir}/tenants.db")
        self._isolation = TenantDataIsolation(tenants_root=f"{data_dir}/tenants")
        self._startup_engine = StartupEngine()
        self._agency_registry = get_agency_registry()
        self._playbook_library = PlaybookLibrary()
        self._workflow_manager = WorkflowStateManager(data_dir=f"{data_dir}/workflows")
        self._usage_manager = UsageManager(data_path=f"{data_dir}/usage/usage_data.json")
        self._admin_manager = AdminManager(self._tenant_manager, self._usage_manager)
        self._initialized = False
        self._init_system()

    def _init_system(self) -> None:
        if self._initialized:
            return
        from pathlib import Path
        Path(self._data_dir).mkdir(parents=True, exist_ok=True)
        self._initialized = True
        logger.info(
            "单创OS v2.0 初始化完成: data_dir=%s, agents=%d, playbooks=%d",
            self._data_dir,
            self._agency_registry.total_count(),
            len(self._playbook_library.list_templates()),
        )

    # ── 租户管理 ──────────────────────────────────────────────────

    def create_tenant(self, name: str, email: str, plan: str = "free",
                      industry: str = "general") -> Dict[str, Any]:
        tenant = self._tenant_manager.create_tenant(name, email, plan, industry)
        if tenant:
            self._isolation.ensure_tenant_space(tenant.tenant_id)
            api_key = self._tenant_manager.generate_api_key(tenant.tenant_id)
            result = tenant.to_dict()
            result["api_key"] = api_key
            logger.info("创建租户: name=%s, plan=%s, industry=%s", name, plan, industry)
            return result
        return {"success": False, "error": "创建租户失败"}

    def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        return tenant.to_dict() if tenant else None

    def list_tenants(self, status: str = None) -> List[Dict[str, Any]]:
        tenants = self._tenant_manager.list_tenants(status)
        return [t.to_dict() for t in tenants]

    def update_plan(self, tenant_id: str, plan: str) -> bool:
        return self._tenant_manager.update_plan(tenant_id, plan)

    def suspend_tenant(self, tenant_id: str) -> bool:
        return self._tenant_manager.suspend_tenant(tenant_id)

    def activate_tenant(self, tenant_id: str) -> bool:
        return self._tenant_manager.activate_tenant(tenant_id)

    def delete_tenant(self, tenant_id: str) -> bool:
        self._isolation.cleanup_tenant_space(tenant_id)
        return self._tenant_manager.delete_tenant(tenant_id)

    def validate_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        tenant = self._tenant_manager.validate_api_key(api_key)
        return tenant.to_dict() if tenant else None

    # ── 套餐与用量 ──────────────────────────────────────────────

    def list_plans(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self._usage_manager.list_plans()]

    def get_plan(self, plan: str) -> Optional[Dict[str, Any]]:
        quota = self._usage_manager.get_plan_quota(plan)
        return quota.to_dict() if quota else None

    def get_usage_report(self, tenant_id: str) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return {"error": "租户不存在"}
        plan_val = tenant.plan.value if hasattr(tenant.plan, 'value') else tenant.plan
        return self._usage_manager.get_usage_report(tenant_id, plan_val)

    def check_quota(self, tenant_id: str, metric: str, amount: int = 1) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "error": "租户不存在"}
        try:
            UsageMetric(metric)
        except ValueError:
            return {"allowed": False, "error": "无效的用量指标"}
        result = self._usage_manager.check_quota(tenant_id, metric)
        remaining = result.get("remaining", 0)
        allowed = result.get("ok", False) and (remaining == -1 or remaining >= amount)
        return {
            "allowed": allowed,
            "current": result.get("used", 0),
            "limit": result.get("quota", 0),
            "remaining": remaining,
        }

    # ── 创业目标调度（经典模式） ────────────────────────────────

    def set_goal(self, tenant_id: str, goal: str,
                 industry: str = None) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant or not tenant.is_active():
            return {"success": False, "error": "租户不存在或未激活"}

        quota_check = self.check_quota(
            tenant_id, UsageMetric.GOAL_SET_COUNT.value, 1,
        )
        if not quota_check["allowed"]:
            return {"success": False, "error": "目标拆解次数已达配额上限，请升级套餐"}

        self._usage_manager.record_usage(tenant_id, UsageMetric.GOAL_SET_COUNT, 1)

        actual_industry = industry or tenant.industry or "general"
        result = self._startup_engine.set_goal(
            tenant_id=tenant_id,
            goal=goal,
            industry=actual_industry,
        )
        return result

    def run_daily(self, tenant_id: str) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant or not tenant.is_active():
            return {"success": False, "error": "租户不存在或未激活"}

        quota_check = self.check_quota(
            tenant_id, UsageMetric.DAILY_RUN_COUNT.value, 1,
        )
        if not quota_check["allowed"]:
            return {"success": False, "error": "每日运行次数已达配额上限"}

        self._usage_manager.record_usage(tenant_id, UsageMetric.DAILY_RUN_COUNT, 1)
        return self._startup_engine.run_daily(tenant_id=tenant_id)

    def get_status(self, tenant_id: str) -> Dict[str, Any]:
        return self._startup_engine.get_status(tenant_id)

    def review_iteration(self, tenant_id: str,
                         iteration: str = "weekly") -> Dict[str, Any]:
        return self._startup_engine.review_iteration(tenant_id, iteration)

    def adjust_strategy(self, tenant_id: str, feedback: str) -> Dict[str, Any]:
        return self._startup_engine.adjust_strategy(tenant_id, feedback)

    # ── Crew 协作编排（CrewAI 式） ─────────────────────────────

    def run_crew_from_template(
        self,
        tenant_id: str,
        template_name: str = "startup_mvp",
    ) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant or not tenant.is_active():
            return {"success": False, "error": "租户不存在或未激活"}

        template = self._playbook_library.get_template(template_name)
        if not template:
            return {"success": False, "error": f"模板不存在: {template_name}"}

        quota_check = self.check_quota(
            tenant_id, UsageMetric.AGENT_CALL_COUNT.value, len(template.steps),
        )
        if not quota_check["allowed"]:
            return {"success": False, "error": "智能体调用次数已达配额上限"}

        crew = CrewOrchestrator(process_type=ProcessType.SEQUENTIAL, verbose=True)

        for role in OPCRole:
            crew.add_agents_from_opc(role, count=1)

        for step in template.steps:
            task = CrewTask(
                name=step.name,
                description=step.description,
                expected_output=", ".join(step.deliverables) if step.deliverables else "",
                agent_role=step.assigned_role,
                opc_role=OPCRole(step.opc_role) if step.opc_role else None,
                dependencies=step.dependencies,
            )
            crew.add_task(task)

        result = crew.kickoff()

        self._usage_manager.record_usage(
            tenant_id, UsageMetric.AGENT_CALL_COUNT, len(template.steps)
        )

        return {
            "success": True,
            "template": template_name,
            "result": result.to_dict(),
        }

    # ── Playbook 工作流 + 状态检查点 ────────────────────────────

    def list_playbooks(self, industry: str = None) -> List[Dict[str, Any]]:
        templates = self._playbook_library.list_templates(industry=industry)
        return [t.to_dict() for t in templates]

    def get_playbook(self, template_id: str) -> Optional[Dict[str, Any]]:
        template = self._playbook_library.get_template(template_id)
        return template.to_dict() if template else None

    def suggest_playbook(self, goal: str, industry: str = "general") -> Dict[str, Any]:
        templates = self._playbook_library.suggest_template(industry=industry, keywords=[goal])
        if templates:
            return templates[0].to_dict()
        return {}

    def create_workflow(
        self,
        tenant_id: str,
        goal: str,
        template_id: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant or not tenant.is_active():
            return {"success": False, "error": "租户不存在或未激活"}

        quota_check = self.check_quota(
            tenant_id, UsageMetric.WORKFLOW_COUNT.value, 1,
        )
        if not quota_check["allowed"]:
            return {"success": False, "error": "工作流数量已达配额上限"}

        if not template_id:
            templates = self._playbook_library.suggest_template(industry=tenant.industry, keywords=[goal])
            if not templates:
                return {"success": False, "error": "无法找到合适的工作流模板"}
            template = templates[0]
            template_id = template.template_id
        else:
            template = self._playbook_library.get_template(template_id)
            if not template:
                return {"success": False, "error": f"模板不存在: {template_id}"}

        metadata = {"tenant_id": tenant_id, "goal": goal}
        if context:
            metadata["context"] = context

        workflow = self._workflow_manager.create_workflow(
            template=template,
            name=goal,
            metadata=metadata,
        )

        result = workflow.to_dict() if hasattr(workflow, 'to_dict') else workflow.__dict__

        self._usage_manager.record_usage(
            tenant_id, UsageMetric.WORKFLOW_COUNT, 1
        )

        return result

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        wf = self._workflow_manager.get_workflow(workflow_id)
        if wf is None:
            return None
        return wf.to_dict() if hasattr(wf, 'to_dict') else wf.__dict__

    def get_workflow_progress(self, workflow_id: str) -> Dict[str, Any]:
        return self._workflow_manager.get_progress(workflow_id)

    def list_workflows(self, tenant_id: str = None) -> List[Dict[str, Any]]:
        wfs = self._workflow_manager.list_workflows()
        if tenant_id:
            wfs = [w for w in wfs if w.metadata and w.metadata.get("tenant_id") == tenant_id]
        return [w.to_dict() if hasattr(w, 'to_dict') else w.__dict__ for w in wfs]

    def start_workflow_step(self, workflow_id: str, step_id: str) -> Dict[str, Any]:
        wf = self._workflow_manager.start_step(workflow_id, step_id)
        return wf.to_dict() if hasattr(wf, 'to_dict') else wf.__dict__

    def complete_workflow_step(
        self,
        workflow_id: str,
        step_id: str,
        output: str = None,
        context_updates: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        wf = self._workflow_manager.complete_step(
            workflow_id, step_id,
            success=True,
            output={"text": output, "context_updates": context_updates} if output or context_updates else None,
        )
        return wf.to_dict() if hasattr(wf, 'to_dict') else wf.__dict__

    def rollback_workflow(self, workflow_id: str, checkpoint_id: str) -> Dict[str, Any]:
        wf = self._workflow_manager.rollback_to_checkpoint(workflow_id, checkpoint_id)
        return wf.to_dict() if hasattr(wf, 'to_dict') else wf.__dict__

    def list_checkpoints(self, workflow_id: str) -> List[Dict[str, Any]]:
        return self._workflow_manager.list_checkpoints(workflow_id)

    # ── Agency 角色库（147+专业角色） ──────────────────────────

    def get_opc_roles(self) -> List[Dict[str, Any]]:
        roles = get_all_roles()
        return [r.to_dict() for r in roles]

    def get_agency_hierarchy(self) -> Dict[str, Any]:
        return self._agency_registry.get_full_hierarchy()

    def list_agency_agents(
        self,
        opc_role: str = None,
        department: str = None,
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        opc_role_enum = OPCRole(opc_role) if opc_role else None
        agents = self._agency_registry.list_agents(
            opc_role=opc_role_enum,
            department=department,
            limit=limit,
        )
        return [a.to_dict() for a in agents]

    def get_agent_detail(self, agent_id: str) -> Optional[Dict[str, Any]]:
        agent = self._agency_registry.get_agent(agent_id)
        return agent.to_dict() if agent else None

    def get_agent_prompt(self, agent_id: str) -> Optional[str]:
        return self._agency_registry.get_agent_prompt(agent_id)

    def search_agents(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        agents = self._agency_registry.search_agents(keyword, limit)
        return [a.to_dict() for a in agents]

    def get_tenant_roles(self, tenant_id: str) -> List[Dict[str, Any]]:
        tenant = self._tenant_manager.get_tenant(tenant_id)
        if not tenant:
            return []
        template = get_template(tenant.industry)
        roles = get_all_roles()
        if template:
            result = []
            for role in roles:
                role_dict = role.to_dict()
                cfg = template.role_config.get(role.role.value, {})
                if cfg:
                    role_dict["industry_enhanced"] = True
                    if "additional_capabilities" in cfg:
                        role_dict["capabilities"].extend(cfg["additional_capabilities"])
                    if "weight" in cfg:
                        role_dict["weight"] = cfg["weight"]
                result.append(role_dict)
            return result
        return [r.to_dict() for r in roles]

    # ── 行业模板 ─────────────────────────────────────────────────

    def list_industries(self) -> List[Dict[str, Any]]:
        templates = list_templates()
        return [t.to_dict() for t in templates]

    def get_industry_template(self, industry: str) -> Optional[Dict[str, Any]]:
        template = get_template(industry)
        return template.to_dict() if template else None

    # ── 平台管理员 API ──────────────────────────────────────────

    def admin_dashboard(self) -> Dict[str, Any]:
        return self._admin_manager.get_dashboard_stats()

    def admin_list_tenants(
        self,
        status: str = None,
        plan: str = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        return self._admin_manager.list_all_tenants(status, plan, page, page_size)

    def admin_tenant_detail(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        return self._admin_manager.get_tenant_detail(tenant_id)

    def admin_suspend_tenant(self, tenant_id: str, reason: str = "") -> bool:
        return self._admin_manager.suspend_tenant(tenant_id, reason)

    def admin_activate_tenant(self, tenant_id: str) -> bool:
        return self._admin_manager.activate_tenant(tenant_id)

    def admin_update_plan(self, tenant_id: str, plan: str) -> bool:
        return self._admin_manager.update_tenant_plan(tenant_id, plan)

    def admin_system_health(self) -> Dict[str, Any]:
        return self._admin_manager.get_system_health()

    # ── 系统状态 ─────────────────────────────────────────────────

    def system_status(self) -> DanchuangOSStatus:
        all_tenants = self._tenant_manager.list_tenants()
        active_tenants = [t for t in all_tenants if t.status == "active"]
        industries = [t.value for t in IndustryType]

        return DanchuangOSStatus(
            tenant_count=len(all_tenants),
            active_tenants=len(active_tenants),
            total_agents=self._agency_registry.total_count(),
            total_playbooks=len(self._playbook_library.list_templates()),
            supported_industries=industries,
        )


# 单例实例
_instance: Optional[DanchuangOS] = None


def get_danchuang_os() -> DanchuangOS:
    """获取单创OS单例。"""
    global _instance
    if _instance is None:
        _instance = DanchuangOS()
    return _instance
