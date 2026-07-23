"""单创OS API v2.0（DanchuangOS API）— 炼化融合版。

提供完整的 AI 一人公司操作系统 REST API 端点。

API 分区：
1. 租户管理：注册、信息、套餐、API Key
2. 套餐用量：套餐列表、用量报告、配额检查
3. 创业调度：目标设定、每日运行、状态、复盘
4. Crew 协作：团队编排、任务执行
5. Playbook 工作流：模板库、实例管理、检查点、回滚
6. Agency 角色库：两级角色体系、角色搜索、Prompt获取
7. 行业模板：行业配置
8. 管理员 API：看板、租户管理、系统健康
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def register_routes(app: FastAPI) -> None:
    """注册单创OS API 路由。

    Args:
        app: FastAPI 应用实例
    """

    router = APIRouter(prefix="/api/danchuang", tags=["danchuang"])

    # ── 请求模型 ────────────────────────────────────────────

    class TenantRegisterRequest(BaseModel):
        name: str = Field(..., description="租户名称")
        email: str = Field(..., description="联系邮箱")
        plan: str = Field("free", description="套餐: free/standard/professional/enterprise")
        industry: str = Field("general", description="行业模板")

    class SetGoalRequest(BaseModel):
        goal: str = Field(..., description="创业目标描述")
        industry: Optional[str] = Field(None, description="行业（默认取租户配置）")

    class ReviewRequest(BaseModel):
        iteration: str = Field("weekly", description="迭代周期: weekly/monthly")

    class AdjustRequest(BaseModel):
        feedback: str = Field(..., description="反馈内容")

    class CreateWorkflowRequest(BaseModel):
        goal: str = Field(..., description="工作流目标")
        template_id: Optional[str] = Field(None, description="模板ID（不传则自动推荐）")
        context: Optional[Dict[str, Any]] = Field(None, description="初始上下文")

    class CompleteStepRequest(BaseModel):
        output: Optional[str] = Field(None, description="步骤产出")
        context_updates: Optional[Dict[str, Any]] = Field(None, description="上下文更新")

    class CrewRunRequest(BaseModel):
        template_name: str = Field("startup_mvp", description="Crew模板名称")

    # ── 辅助函数 ────────────────────────────────────────────

    def _get_os():
        from kernel.danchuang import get_danchuang_os
        return get_danchuang_os()

    def _get_tenant_from_key(x_api_key: Optional[str]):
        if not x_api_key:
            raise HTTPException(status_code=401, detail="缺少 API Key")
        os = _get_os()
        tenant = os.validate_api_key(x_api_key)
        if not tenant:
            raise HTTPException(status_code=401, detail="API Key 无效")
        return tenant

    def _verify_admin(x_admin_key: Optional[str]):
        """简易管理员验证（生产环境应使用更严格的认证）。"""
        import os
        admin_key = os.environ.get("DANCHUANG_ADMIN_KEY", "admin-danchuang-2026")
        if not x_admin_key or x_admin_key != admin_key:
            raise HTTPException(status_code=403, detail="管理员权限不足")
        return True

    # ═══════════════════════════════════════════════════════
    #  第一区：租户管理
    # ═══════════════════════════════════════════════════════

    @router.post("/tenant/register", summary="注册新租户")
    async def register_tenant(req: TenantRegisterRequest):
        try:
            os = _get_os()
            tenant = os.create_tenant(req.name, req.email, req.plan, req.industry)
            return tenant
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("注册租户失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/tenant", summary="获取当前租户信息")
    async def get_tenant(x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        return tenant

    @router.put("/tenant/plan", summary="升级/降级套餐")
    async def update_plan(plan: str, x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        success = os.update_plan(tenant["tenant_id"], plan)
        return {"success": success}

    # ═══════════════════════════════════════════════════════
    #  第二区：套餐与用量
    # ═══════════════════════════════════════════════════════

    @router.get("/plans", summary="列出所有套餐")
    async def list_plans():
        os = _get_os()
        return {"plans": os.list_plans()}

    @router.get("/plans/{plan_id}", summary="获取套餐详情")
    async def get_plan(plan_id: str):
        os = _get_os()
        plan = os.get_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="套餐不存在")
        return plan

    @router.get("/usage", summary="获取当前租户用量报告")
    async def get_usage(x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.get_usage_report(tenant["tenant_id"])

    @router.get("/quota/check", summary="检查配额")
    async def check_quota(
        metric: str,
        amount: int = 1,
        x_api_key: Optional[str] = Header(None),
    ):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.check_quota(tenant["tenant_id"], metric, amount)

    # ═══════════════════════════════════════════════════════
    #  第三区：创业目标调度（经典模式）
    # ═══════════════════════════════════════════════════════

    @router.post("/goal/set", summary="设定创业目标并自动拆解")
    async def set_goal(req: SetGoalRequest, x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        result = os.set_goal(tenant["tenant_id"], req.goal, req.industry)
        return result

    @router.post("/daily/run", summary="执行每日创业工作流")
    async def run_daily(x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        result = os.run_daily(tenant["tenant_id"])
        return result

    @router.get("/status", summary="获取创业状态总览")
    async def get_status(x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.get_status(tenant["tenant_id"])

    @router.post("/review", summary="迭代复盘")
    async def review_iteration(req: ReviewRequest, x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.review_iteration(tenant["tenant_id"], req.iteration)

    @router.post("/adjust", summary="根据反馈调整策略")
    async def adjust_strategy(req: AdjustRequest, x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.adjust_strategy(tenant["tenant_id"], req.feedback)

    # ═══════════════════════════════════════════════════════
    #  第四区：Crew 协作编排
    # ═══════════════════════════════════════════════════════

    @router.post("/crew/run", summary="从模板运行Crew协作")
    async def run_crew(req: CrewRunRequest, x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        result = os.run_crew_from_template(tenant["tenant_id"], req.template_name)
        return result

    # ═══════════════════════════════════════════════════════
    #  第五区：Playbook 工作流 + 状态检查点
    # ═══════════════════════════════════════════════════════

    @router.get("/playbooks", summary="列出工作流模板")
    async def list_playbooks(industry: Optional[str] = Query(None, description="按行业筛选")):
        os = _get_os()
        return {"playbooks": os.list_playbooks(industry=industry)}

    @router.get("/playbooks/{template_id}", summary="获取工作流模板详情")
    async def get_playbook(template_id: str):
        os = _get_os()
        template = os.get_playbook(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="模板不存在")
        return template

    @router.get("/playbooks/suggest", summary="根据目标推荐模板")
    async def suggest_playbook(goal: str, industry: str = "general"):
        os = _get_os()
        return os.suggest_playbook(goal, industry)

    @router.post("/workflows", summary="创建工作流实例")
    async def create_workflow(
        req: CreateWorkflowRequest,
        x_api_key: Optional[str] = Header(None),
    ):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.create_workflow(
            tenant["tenant_id"], req.goal, req.template_id, req.context
        )

    @router.get("/workflows", summary="列出工作流")
    async def list_workflows(x_api_key: Optional[str] = Header(None)):
        tenant = _get_tenant_from_key(x_api_key)
        os = _get_os()
        return {"workflows": os.list_workflows(tenant["tenant_id"])}

    @router.get("/workflows/{workflow_id}", summary="获取工作流详情")
    async def get_workflow(workflow_id: str, x_api_key: Optional[str] = Header(None)):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        wf = os.get_workflow(workflow_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return wf

    @router.get("/workflows/{workflow_id}/progress", summary="获取工作流进度")
    async def get_workflow_progress(workflow_id: str, x_api_key: Optional[str] = Header(None)):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.get_workflow_progress(workflow_id)

    @router.post("/workflows/{workflow_id}/steps/{step_id}/start", summary="启动工作流步骤")
    async def start_step(
        workflow_id: str,
        step_id: str,
        x_api_key: Optional[str] = Header(None),
    ):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.start_workflow_step(workflow_id, step_id)

    @router.post("/workflows/{workflow_id}/steps/{step_id}/complete", summary="完成工作流步骤")
    async def complete_step(
        workflow_id: str,
        step_id: str,
        req: CompleteStepRequest,
        x_api_key: Optional[str] = Header(None),
    ):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.complete_workflow_step(
            workflow_id, step_id, req.output, req.context_updates
        )

    @router.get("/workflows/{workflow_id}/checkpoints", summary="列出检查点")
    async def list_checkpoints(workflow_id: str, x_api_key: Optional[str] = Header(None)):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        return {"checkpoints": os.list_checkpoints(workflow_id)}

    @router.post("/workflows/{workflow_id}/rollback", summary="回滚到指定检查点")
    async def rollback_workflow(
        workflow_id: str,
        checkpoint_id: str,
        x_api_key: Optional[str] = Header(None),
    ):
        _get_tenant_from_key(x_api_key)
        os = _get_os()
        return os.rollback_workflow(workflow_id, checkpoint_id)

    # ═══════════════════════════════════════════════════════
    #  第六区：Agency 角色库（147+专业角色）
    # ═══════════════════════════════════════════════════════

    @router.get("/agency/hierarchy", summary="获取两级角色体系")
    async def get_agency_hierarchy():
        os = _get_os()
        return os.get_agency_hierarchy()

    @router.get("/agency/agents", summary="列出专业角色")
    async def list_agency_agents(
        opc_role: Optional[str] = Query(None, description="按OPC岗位筛选"),
        department: Optional[str] = Query(None, description="按部门筛选"),
        limit: Optional[int] = Query(None, description="返回数量限制"),
    ):
        os = _get_os()
        return {"agents": os.list_agency_agents(opc_role, department, limit)}

    @router.get("/agency/agents/{agent_id}", summary="获取角色详情")
    async def get_agent_detail(agent_id: str):
        os = _get_os()
        agent = os.get_agent_detail(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="角色不存在")
        return agent

    @router.get("/agency/agents/{agent_id}/prompt", summary="获取角色System Prompt")
    async def get_agent_prompt(agent_id: str):
        os = _get_os()
        prompt = os.get_agent_prompt(agent_id)
        if not prompt:
            raise HTTPException(status_code=404, detail="角色不存在")
        return {"agent_id": agent_id, "prompt": prompt}

    @router.get("/agency/search", summary="搜索专业角色")
    async def search_agents(keyword: str, limit: int = 10):
        os = _get_os()
        return {"agents": os.search_agents(keyword, limit)}

    # ═══════════════════════════════════════════════════════
    #  第七区：行业模板
    # ═══════════════════════════════════════════════════════

    @router.get("/industries", summary="列出所有行业模板")
    async def list_industries():
        os = _get_os()
        return {"industries": os.list_industries()}

    @router.get("/industries/{industry_id}", summary="获取行业模板详情")
    async def get_industry(industry_id: str):
        os = _get_os()
        template = os.get_industry_template(industry_id)
        if not template:
            raise HTTPException(status_code=404, detail="行业模板不存在")
        return template

    # ═══════════════════════════════════════════════════════
    #  第八区：平台管理员 API
    # ═══════════════════════════════════════════════════════

    @router.get("/admin/dashboard", summary="管理员看板统计")
    async def admin_dashboard(x_admin_key: Optional[str] = Header(None)):
        _verify_admin(x_admin_key)
        os = _get_os()
        return os.admin_dashboard()

    @router.get("/admin/tenants", summary="管理员：列出所有租户")
    async def admin_list_tenants(
        status: Optional[str] = None,
        plan: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        x_admin_key: Optional[str] = Header(None),
    ):
        _verify_admin(x_admin_key)
        os = _get_os()
        return os.admin_list_tenants(status, plan, page, page_size)

    @router.get("/admin/tenants/{tenant_id}", summary="管理员：租户详情")
    async def admin_tenant_detail(tenant_id: str, x_admin_key: Optional[str] = Header(None)):
        _verify_admin(x_admin_key)
        os = _get_os()
        detail = os.admin_tenant_detail(tenant_id)
        if not detail:
            raise HTTPException(status_code=404, detail="租户不存在")
        return detail

    @router.post("/admin/tenants/{tenant_id}/suspend", summary="管理员：暂停租户")
    async def admin_suspend_tenant(
        tenant_id: str,
        reason: str = "",
        x_admin_key: Optional[str] = Header(None),
    ):
        _verify_admin(x_admin_key)
        os = _get_os()
        success = os.admin_suspend_tenant(tenant_id, reason)
        return {"success": success}

    @router.post("/admin/tenants/{tenant_id}/activate", summary="管理员：激活租户")
    async def admin_activate_tenant(
        tenant_id: str,
        x_admin_key: Optional[str] = Header(None),
    ):
        _verify_admin(x_admin_key)
        os = _get_os()
        success = os.admin_activate_tenant(tenant_id)
        return {"success": success}

    @router.put("/admin/tenants/{tenant_id}/plan", summary="管理员：更新租户套餐")
    async def admin_update_plan(
        tenant_id: str,
        plan: str,
        x_admin_key: Optional[str] = Header(None),
    ):
        _verify_admin(x_admin_key)
        os = _get_os()
        success = os.admin_update_plan(tenant_id, plan)
        return {"success": success}

    @router.get("/admin/system/health", summary="管理员：系统健康状态")
    async def admin_system_health(x_admin_key: Optional[str] = Header(None)):
        _verify_admin(x_admin_key)
        os = _get_os()
        return os.admin_system_health()

    # ═══════════════════════════════════════════════════════
    #  系统状态
    # ═══════════════════════════════════════════════════════

    @router.get("/system/status", summary="获取系统整体状态")
    async def system_status():
        os = _get_os()
        return os.system_status().to_dict()

    # ═══════════════════════════════════════════════════════
    #  第九区：BYOK 模型供应商（自助填 Key + 加密隔离）
    # ═══════════════════════════════════════════════════════

    class ByokSaveRequest(BaseModel):
        provider: str = Field(..., description="供应商 id，见 /byok/presets")
        api_key: str = Field(..., description="用户自己的 API Key")
        model: Optional[str] = Field(None, description="模型 id，默认取预设首个")
        api_base: Optional[str] = Field(None, description="自定义端点，默认取预设")
        is_default: bool = Field(False, description="是否设为租户默认")

    class ByokTestRequest(BaseModel):
        provider: str = Field(..., description="供应商 id")
        api_key: str = Field(..., description="待测试的 API Key")
        model: Optional[str] = Field(None, description="模型 id")
        api_base: Optional[str] = Field(None, description="自定义端点")

    class ByokChatRequest(BaseModel):
        prompt: str = Field(..., description="对话内容")
        provider: Optional[str] = Field(None, description="指定供应商，缺省用租户默认")

    try:
        from kernel.danchuang.tenant.byok import ByokStore
        _byok = ByokStore()

        @router.get("/byok/presets", summary="列出可填 Key 的国内主流模型供应商")
        async def byok_presets():
            return {"providers": _byok.list_presets()}

        @router.post("/byok/test", summary="用真实 Key 测试供应商连通性")
        async def byok_test(req: ByokTestRequest, x_api_key: Optional[str] = Header(None)):
            _get_tenant_from_key(x_api_key)
            return _byok.test_provider(req.provider, req.api_key, req.model, req.api_base)

        @router.post("/byok/save", summary="保存（加密）供应商 Key")
        async def byok_save(req: ByokSaveRequest, x_api_key: Optional[str] = Header(None)):
            tenant = _get_tenant_from_key(x_api_key)
            tid = tenant["tenant_id"] if isinstance(tenant, dict) else tenant.tenant_id
            return _byok.save(tid, req.provider, req.api_key, req.model, req.api_base, req.is_default)

        @router.get("/byok/list", summary="列出本租户已保存的供应商")
        async def byok_list(x_api_key: Optional[str] = Header(None)):
            tenant = _get_tenant_from_key(x_api_key)
            tid = tenant["tenant_id"] if isinstance(tenant, dict) else tenant.tenant_id
            return {"keys": _byok.list_keys(tid)}

        @router.delete("/byok/{provider}", summary="删除供应商 Key")
        async def byok_delete(provider: str, x_api_key: Optional[str] = Header(None)):
            tenant = _get_tenant_from_key(x_api_key)
            tid = tenant["tenant_id"] if isinstance(tenant, dict) else tenant.tenant_id
            return {"success": _byok.delete(tid, provider)}

        @router.put("/byok/{provider}/default", summary="设为租户默认供应商")
        async def byok_set_default(provider: str, x_api_key: Optional[str] = Header(None)):
            tenant = _get_tenant_from_key(x_api_key)
            tid = tenant["tenant_id"] if isinstance(tenant, dict) else tenant.tenant_id
            return {"success": _byok.set_default(tid, provider)}

        @router.post("/byok/chat", summary="用本租户模型供应商直接对话（验证闭环）")
        async def byok_chat(req: ByokChatRequest, x_api_key: Optional[str] = Header(None)):
            tenant = _get_tenant_from_key(x_api_key)
            tid = tenant["tenant_id"] if isinstance(tenant, dict) else tenant.tenant_id
            return _byok.chat(tid, req.prompt, req.provider)

    except Exception as e:  # BYOK 模块异常不应拖垮整个 API
        logger.error("BYOK 路由加载失败（已跳过）: %s", e, exc_info=True)

    app.include_router(router)
    logger.info("单创OS API v2.0 已挂载: /api/danchuang (含 BYOK 第九区)")
