"""产品飞轮 API —— Studio / Hub / Pulse / Evolve 的 HTTP 接口。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/studio", tags=["studio"])

# ── Pydantic 模型 ──

class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    author: str = "user"


class AddStepRequest(BaseModel):
    capability: str
    name: str = ""
    in_from: str = "previous"
    prompt: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)


class MoveStepRequest(BaseModel):
    step_id: str
    new_index: int


class SaveWorkflowRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    steps: Optional[List[Dict[str, Any]]] = None
    new_version: bool = False


class RunWorkflowRequest(BaseModel):
    input: Dict[str, Any] = Field(default_factory=dict)


class UseTemplateRequest(BaseModel):
    new_name: str = ""
    author: str = "user"


class HubReviewRequest(BaseModel):
    user: str
    rating: int
    comment: str = ""


# ── 工具函数 ──

def _get_store(request: Request):
    from kernel.studio.workflow_store import get_workflow_store
    return get_workflow_store()


def _get_runner(request: Request):
    from kernel.studio.workflow_runner import get_workflow_runner
    return get_workflow_runner()


def _get_hub(request: Request):
    from kernel.hub.hub_store import get_hub_store
    return get_hub_store()


def _get_pulse(request: Request):
    from kernel.pulse.pulse_collector import get_pulse_collector
    return get_pulse_collector()


def _get_evolve(request: Request):
    from kernel.evolve.evolve_engine import get_evolve_engine
    return get_evolve_engine()


# ═══════════════════════════════════════════
#  Studio —— 工作流管理
# ═══════════════════════════════════════════

@router.get("/workflows")
async def list_workflows(
    request: Request,
    category: str = "",
    tag: str = "",
    search: str = "",
    is_template: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出工作流。"""
    try:
        store = _get_store(request)
        items = store.list(
            category=category,
            tag=tag,
            is_template=is_template,
            search=search,
            limit=limit,
            offset=offset,
        )
        return {"status": "ok", "total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows")
async def create_workflow(request: Request, body: CreateWorkflowRequest):
    """创建新工作流。"""
    try:
        store = _get_store(request)
        wf = store.create(name=body.name, description=body.description, author=body.author)
        return {"status": "ok", "workflow": wf.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{wf_id}")
async def get_workflow(request: Request, wf_id: str):
    """获取工作流详情。"""
    try:
        store = _get_store(request)
        wf = store.get(wf_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"status": "ok", "workflow": wf.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/workflows/{wf_id}")
async def save_workflow(request: Request, wf_id: str, body: SaveWorkflowRequest):
    """保存工作流。"""
    try:
        store = _get_store(request)
        wf = store.get(wf_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")

        if body.name is not None:
            wf.name = body.name
        if body.description is not None:
            wf.description = body.description
        if body.category is not None:
            wf.category = body.category
        if body.tags is not None:
            wf.tags = body.tags
        if body.steps is not None:
            from kernel.studio.workflow_models import WorkflowStep
            wf.steps = [WorkflowStep(**s) for s in body.steps]

        saved = store.save(wf, new_version=body.new_version)
        return {"status": "ok", "workflow": saved.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflows/{wf_id}")
async def delete_workflow(request: Request, wf_id: str):
    """删除工作流。"""
    try:
        store = _get_store(request)
        ok = store.delete(wf_id)
        if not ok:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{wf_id}/steps")
async def add_step(request: Request, wf_id: str, body: AddStepRequest):
    """添加步骤。"""
    try:
        store = _get_store(request)
        wf = store.get(wf_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")

        step = wf.add_step(
            capability=body.capability,
            name=body.name,
            in_from=body.in_from,
            prompt=body.prompt,
            payload=body.payload,
        )
        store.save(wf)
        return {"status": "ok", "step": step.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/workflows/{wf_id}/steps/{step_id}")
async def remove_step(request: Request, wf_id: str, step_id: str):
    """删除步骤。"""
    try:
        store = _get_store(request)
        wf = store.get(wf_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")

        ok = wf.remove_step(step_id)
        if not ok:
            raise HTTPException(status_code=404, detail="步骤不存在")
        store.save(wf)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{wf_id}/steps/move")
async def move_step(request: Request, wf_id: str, body: MoveStepRequest):
    """移动步骤顺序。"""
    try:
        store = _get_store(request)
        wf = store.get(wf_id)
        if not wf:
            raise HTTPException(status_code=404, detail="工作流不存在")

        ok = wf.move_step(body.step_id, body.new_index)
        if not ok:
            raise HTTPException(status_code=400, detail="移动失败")
        store.save(wf)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{wf_id}/versions")
async def list_versions(request: Request, wf_id: str):
    """列出所有版本。"""
    try:
        store = _get_store(request)
        versions = store.list_versions(wf_id)
        return {"status": "ok", "versions": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{wf_id}/versions/{version}")
async def get_version(request: Request, wf_id: str, version: str):
    """获取指定版本。"""
    try:
        store = _get_store(request)
        wf = store.get_version(wf_id, version)
        if not wf:
            raise HTTPException(status_code=404, detail="版本不存在")
        return {"status": "ok", "workflow": wf.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{wf_id}/versions/{version}/revert")
async def revert_version(request: Request, wf_id: str, version: str):
    """回退到指定版本。"""
    try:
        store = _get_store(request)
        wf = store.revert_to_version(wf_id, version)
        if not wf:
            raise HTTPException(status_code=404, detail="版本不存在")
        return {"status": "ok", "workflow": wf.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/workflows/{wf_id}/run")
async def run_workflow(request: Request, wf_id: str, body: RunWorkflowRequest):
    """运行工作流。"""
    try:
        runner = _get_runner(request)
        run = await asyncio.to_thread(runner.run, wf_id, input_data=body.input)
        return {
            "status": "ok",
            "run_id": run.id,
            "run_status": run.status,
            "duration": run.duration,
            "output": run.output,
            "steps": run.steps,
            "error": run.error,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{wf_id}/runs")
async def list_runs(request: Request, wf_id: str, limit: int = 20):
    """列出运行历史。"""
    try:
        store = _get_store(request)
        runs = store.list_runs(wf_id, limit=limit)
        return {"status": "ok", "runs": runs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  模板市场
# ═══════════════════════════════════════════

@router.get("/templates")
async def list_templates(
    request: Request,
    category: str = "",
    search: str = "",
    limit: int = 50,
    offset: int = 0,
):
    """列出模板。"""
    try:
        from kernel.studio.template_market import list_templates
        items = list_templates(category=category, search=search)
        items = items[offset:offset + limit]
        return {"status": "ok", "total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/use")
async def use_template(request: Request, template_id: str, body: UseTemplateRequest):
    """基于模板创建新工作流。"""
    try:
        from kernel.studio.template_market import use_template
        wf = use_template(template_id, new_name=body.new_name, author=body.author)
        if not wf:
            raise HTTPException(status_code=404, detail="模板不存在")
        return {"status": "ok", "workflow": wf.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  Hub —— 智能体商店
# ═══════════════════════════════════════════

hub_router = APIRouter(prefix="/api/hub", tags=["hub"])


@hub_router.get("/agents")
async def hub_list_agents(
    request: Request,
    category: str = "",
    tag: str = "",
    sort: str = "popular",
    search: str = "",
    limit: int = 20,
    offset: int = 0,
):
    """列出智能体。"""
    try:
        hub = _get_hub(request)
        items = hub.list_agents(
            category=category,
            tag=tag,
            sort=sort,
            search=search,
            limit=limit,
            offset=offset,
        )
        return {"status": "ok", "total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.get("/agents/{agent_id}")
async def hub_get_agent(request: Request, agent_id: str):
    """获取智能体详情。"""
    try:
        hub = _get_hub(request)
        agent = hub.get_agent(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"status": "ok", "agent": agent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.post("/agents/{agent_id}/use")
async def hub_use_agent(request: Request, agent_id: str, body: RunWorkflowRequest):
    """使用智能体（运行）。"""
    try:
        hub = _get_hub(request)
        result = await asyncio.to_thread(hub.use_agent, agent_id, body.input)
        if not result:
            raise HTTPException(status_code=404, detail="智能体不存在")
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.get("/agents/{agent_id}/reviews")
async def hub_get_reviews(request: Request, agent_id: str, limit: int = 20):
    """获取评论。"""
    try:
        hub = _get_hub(request)
        reviews = hub.get_reviews(agent_id, limit=limit)
        return {"status": "ok", "reviews": reviews}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.post("/agents/{agent_id}/reviews")
async def hub_add_review(request: Request, agent_id: str, body: HubReviewRequest):
    """添加评价。"""
    try:
        hub = _get_hub(request)
        ok = hub.add_review(agent_id, user=body.user, rating=body.rating, comment=body.comment)
        if not ok:
            raise HTTPException(status_code=400, detail="评分无效")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.get("/categories")
async def hub_categories(request: Request):
    """列出分类。"""
    try:
        hub = _get_hub(request)
        categories = hub.list_categories()
        return {"status": "ok", "categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.post("/agents/{workflow_id}/publish")
async def hub_publish(request: Request, workflow_id: str):
    """发布到 Hub。"""
    try:
        hub = _get_hub(request)
        ok = hub.publish(workflow_id)
        if not ok:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@hub_router.post("/agents/{workflow_id}/unpublish")
async def hub_unpublish(request: Request, workflow_id: str):
    """从 Hub 下架。"""
    try:
        hub = _get_hub(request)
        ok = hub.unpublish(workflow_id)
        if not ok:
            raise HTTPException(status_code=404, detail="工作流不存在")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  Pulse —— 数据采集
# ═══════════════════════════════════════════

pulse_router = APIRouter(prefix="/api/pulse", tags=["pulse"])


@pulse_router.get("/metrics")
async def pulse_list_metrics(request: Request, limit: int = 50):
    """获取所有智能体的指标。"""
    try:
        pulse = _get_pulse(request)
        metrics = pulse.get_all_metrics(limit=limit)
        return {"status": "ok", "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.get("/metrics/{workflow_id}")
async def pulse_agent_metrics(request: Request, workflow_id: str):
    """获取单个智能体的指标。"""
    try:
        pulse = _get_pulse(request)
        metrics = pulse.get_agent_metrics(workflow_id)
        return {"status": "ok", "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.get("/failures/{workflow_id}")
async def pulse_failure_analysis(request: Request, workflow_id: str):
    """失败分析。"""
    try:
        pulse = _get_pulse(request)
        analysis = pulse.get_failure_analysis(workflow_id)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 成本可观测（Task 1: Cost Observability）──

@pulse_router.get("/costs")
async def pulse_cost_breakdown(
    request: Request,
    workflow_id: str = "",
    user_id: str = "",
    agent_id: str = "",
    since: str = "",
    until: str = "",
    limit: int = 10000,
):
    """获取成本聚合（按 model/workflow/user/agent 维度）。

    Query 参数：
    - workflow_id / user_id / agent_id: 过滤维度（空字符串=不过滤）
    - since / until: ISO 时间前缀过滤（如 "2026-07" 过滤整月）
    - limit: 最多扫描多少条事件
    """
    try:
        pulse = _get_pulse(request)
        result = pulse.get_cost_breakdown(
            workflow_id=workflow_id, user_id=user_id,
            agent_id=agent_id, since=since, until=until, limit=limit,
        )
        return {"status": "ok", "cost": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.get("/costs/records")
async def pulse_cost_records(
    request: Request,
    limit: int = 50,
    workflow_id: str = "",
):
    """获取最近 N 条成本事件（按时间倒序）。"""
    try:
        pulse = _get_pulse(request)
        records = pulse.get_cost_records(limit=limit, workflow_id=workflow_id)
        return {"status": "ok", "records": records, "count": len(records)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateCostAlertRequest(BaseModel):
    name: str
    scope: str = "global"  # global / workflow / user / agent
    scope_id: str = ""
    period: str = "daily"  # daily / monthly
    threshold_usd: float = 1.0


@pulse_router.post("/costs/alerts")
async def pulse_create_cost_alert(request: Request, body: CreateCostAlertRequest):
    """创建一个成本告警。"""
    try:
        pulse = _get_pulse(request)
        result = pulse.add_cost_alert(
            name=body.name, scope=body.scope, scope_id=body.scope_id,
            period=body.period, threshold_usd=body.threshold_usd,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "创建失败"))
        return {"status": "ok", "alert_id": result["alert_id"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.get("/costs/alerts")
async def pulse_list_cost_alerts(request: Request, enabled_only: bool = False):
    """列出所有成本告警。"""
    try:
        pulse = _get_pulse(request)
        alerts = pulse.list_cost_alerts(enabled_only=enabled_only)
        return {"status": "ok", "alerts": alerts, "count": len(alerts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.delete("/costs/alerts/{alert_id}")
async def pulse_delete_cost_alert(request: Request, alert_id: str):
    """删除一个成本告警。"""
    try:
        pulse = _get_pulse(request)
        ok = pulse.delete_cost_alert(alert_id)
        if not ok:
            raise HTTPException(status_code=404, detail="告警不存在")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@pulse_router.post("/costs/alerts/check")
async def pulse_check_cost_alerts(request: Request):
    """主动触发成本告警检查，返回触发的告警列表。"""
    try:
        pulse = _get_pulse(request)
        triggered = pulse.check_cost_alerts()
        return {"status": "ok", "triggered": triggered, "count": len(triggered)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  Evolve —— 自动进化
# ═══════════════════════════════════════════

evolve_router = APIRouter(prefix="/api/evolve", tags=["evolve"])


@evolve_router.get("/ab-tests")
async def evolve_list_tests(
    request: Request,
    workflow_id: str = "",
    status: str = "",
):
    """列出 A/B 测试。"""
    try:
        evolve = _get_evolve(request)
        tests = evolve.list_tests(workflow_id=workflow_id, status=status)
        return {"status": "ok", "tests": tests}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/ab-tests")
async def evolve_create_test(request: Request, body: Dict[str, Any]):
    """创建 A/B 测试。"""
    try:
        evolve = _get_evolve(request)
        test = evolve.create_ab_test(
            workflow_id=body.get("workflow_id", ""),
            name=body.get("name", ""),
            variant_a=body.get("variant_a", {}),
            variant_b=body.get("variant_b", {}),
            metric=body.get("metric", "success_rate"),
        )
        from dataclasses import asdict
        return {"status": "ok", "test": asdict(test)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/ab-tests/{test_id}/stop")
async def evolve_stop_test(request: Request, test_id: str):
    """停止 A/B 测试。"""
    try:
        evolve = _get_evolve(request)
        ok = evolve.stop_test(test_id)
        if not ok:
            raise HTTPException(status_code=404, detail="测试不存在")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.get("/suggestions/{workflow_id}")
async def evolve_suggestions(request: Request, workflow_id: str):
    """获取优化建议。"""
    try:
        evolve = _get_evolve(request)
        pulse = _get_pulse(request)
        metrics = pulse.get_agent_metrics(workflow_id)
        suggestions = evolve.suggest_optimizations(workflow_id, metrics)
        return {"status": "ok", "suggestions": suggestions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 优化提案系统（闭环写回）──

@evolve_router.get("/proposals/{workflow_id}")
async def evolve_list_proposals(request: Request, workflow_id: str):
    """列出工作流的优化提案。"""
    try:
        evolve = _get_evolve(request)
        proposals = evolve.list_proposals(workflow_id)
        from dataclasses import asdict
        return {"status": "ok", "proposals": [asdict(p) for p in proposals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/proposals/{workflow_id}/generate")
async def evolve_generate_proposals(request: Request, workflow_id: str):
    """生成工作流的优化提案。"""
    try:
        evolve = _get_evolve(request)
        proposals = evolve.generate_proposals(workflow_id)
        from dataclasses import asdict
        return {"status": "ok", "count": len(proposals), "proposals": [asdict(p) for p in proposals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ApplyProposalRequest(BaseModel):
    proposal_id: str


@evolve_router.post("/proposals/apply")
async def evolve_apply_proposal(request: Request, body: ApplyProposalRequest):
    """应用一个优化提案。"""
    try:
        evolve = _get_evolve(request)
        store = _get_store(request)
        result = evolve.apply_proposal(body.proposal_id, store)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "应用失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/proposals/{proposal_id}/rollback")
async def evolve_rollback_proposal(request: Request, proposal_id: str):
    """回滚一个已应用的提案。"""
    try:
        evolve = _get_evolve(request)
        store = _get_store(request)
        result = evolve.rollback_proposal(proposal_id, store)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "回滚失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/proposals/{workflow_id}/auto-apply")
async def evolve_auto_apply(request: Request, workflow_id: str):
    """自动应用低风险提案。"""
    try:
        evolve = _get_evolve(request)
        store = _get_store(request)
        results = evolve.auto_apply_low_risk(workflow_id, store)
        return {"status": "ok", "applied_count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 双飞轮互驱 ──

class CrossFlywheelRequest(BaseModel):
    direction: str = "both"  # content_to_product / product_to_content / both


@evolve_router.post("/cross-flywheel")
async def evolve_cross_flywheel(request: Request, body: CrossFlywheelRequest):
    """双飞轮互驱桥接——内容驱动产品，产品驱动内容。"""
    try:
        evolve = _get_evolve(request)
        store = _get_store(request)
        hub = _get_hub(request)
        result = evolve.cross_flywheel_bridge(
            direction=body.direction,
            workflow_store=store,
            hub_store=hub,
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 内容分析 ──

@evolve_router.get("/content-analysis")
async def evolve_content_analysis(request: Request, keyword: str = ""):
    """内容反馈分析。"""
    try:
        evolve = _get_evolve(request)
        analysis = evolve.analyze_content_feedback(keyword)
        return {"status": "ok", "analysis": analysis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@evolve_router.post("/content-proposals")
async def evolve_content_proposals(request: Request, keyword: str = ""):
    """生成内容优化提案。"""
    try:
        evolve = _get_evolve(request)
        proposals = evolve.generate_content_proposals(keyword)
        from dataclasses import asdict
        return {"status": "ok", "count": len(proposals), "proposals": [asdict(p) for p in proposals]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════
#  挂载所有 router
# ═══════════════════════════════════════════

def mount_product_flywheel(app):
    """把产品飞轮的 API 挂载到 FastAPI app 上。"""
    app.include_router(router)
    app.include_router(hub_router)
    app.include_router(pulse_router)
    app.include_router(evolve_router)
    app.include_router(approvals_router)
    logger.info("产品飞轮 API 已挂载: /api/studio, /api/hub, /api/pulse, /api/evolve, /api/proposals")


# ═══════════════════════════════════════════
#  HITL —— 人机协作审批（/api/approvals）
# ═══════════════════════════════════════════

# 注意：规范的、持久化、可审计的审批 API 在 api/approval_api.py（/api/approvals，
# 单一真相：所有 Evolve 提案 / WorkflowRunner 步骤 / Autopilot 操作的审批统一走它）。
# 本 router 仅服务「产品飞轮」的 evolve 提案审批 UI，故使用独立命名空间 /api/proposals，
# 避免与 /api/approvals 撞车导致规范实现被遮蔽（双轨债 ④）。
approvals_router = APIRouter(prefix="/api/proposals", tags=["proposals"])


@approvals_router.get("")
async def list_approvals(request: Request, workflow_id: str = ""):
    """列出待人工确认的高/中风险提案。"""
    try:
        evolve = _get_evolve(request)
        pending = evolve.list_pending_approvals(workflow_id=workflow_id)
        from dataclasses import asdict
        return {"ok": True, "count": len(pending),
                "pending": [asdict(p) for p in pending]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@approvals_router.post("/{proposal_id}/approve")
async def approve_proposal(request: Request, proposal_id: str):
    """确认并通过一个提案（中高风险需此步才应用）。"""
    try:
        evolve = _get_evolve(request)
        store = _get_store(request)
        result = evolve.approve_proposal(proposal_id, store)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "确认失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@approvals_router.post("/{proposal_id}/reject")
async def reject_proposal(request: Request, proposal_id: str, body: Dict[str, Any] = {}):
    """拒绝一个提案。"""
    try:
        evolve = _get_evolve(request)
        reason = (body or {}).get("reason", "")
        result = evolve.reject_proposal(proposal_id, reason=reason)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("error", "拒绝失败"))
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@approvals_router.get("/panel", response_class=HTMLResponse)
async def approvals_panel():
    """Studio 审批面板（最小前端）：拉取待审提案并支持确认/拒绝。"""
    return HTMLResponse(_APPROVAL_PANEL_HTML)


_APPROVAL_PANEL_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>AOS 提案审批面板</title>
<style>
 body{font-family:system-ui,"Microsoft YaHei",sans-serif;max-width:880px;margin:24px auto;padding:0 16px;color:#222}
 h1{font-size:20px} .card{border:1px solid #e3e3e3;border-radius:8px;padding:14px;margin:12px 0}
 .meta{color:#888;font-size:12px} .tag{padding:2px 8px;border-radius:10px;font-size:12px}
 .high{background:#fde8e8;color:#c0392b} .medium{background:#fff4e0;color:#b9770e}
 button{cursor:pointer;border:none;border-radius:6px;padding:6px 14px;margin-right:8px;font-size:13px}
 .ok{background:#2ecc71;color:#fff} .no{background:#e74c3c;color:#fff}
</style></head><body>
<h1>AOS 提案审批面板（HITL）</h1>
<p class="meta">仅中/高风险提案进入此队列，低风险已由系统自动应用。</p>
<div id="list">加载中…</div>
<script>
async function load(){
  const r = await fetch('/api/proposals');
  const j = await r.json();
  const el = document.getElementById('list');
  if(!j.ok || !j.pending.length){ el.innerHTML = '<p>暂无待审提案 ✓</p>'; return; }
  el.innerHTML = j.pending.map(p=>`
    <div class="card">
      <span class="tag ${p.risk_level}">${p.risk_level}</span>
      <b>${p.title}</b> <span class="meta">[${p.proposal_type}]</span>
      <p>${p.description||''}</p>
      <p class="meta">预期收益：${p.expected_benefit||'-'} ｜ 来源：${p.source}</p>
      <button class="ok" onclick="act('${p.id}','approve')">确认通过</button>
      <button class="no" onclick="act('${p.id}','reject')">拒绝</button>
    </div>`).join('');
}
async function act(id, op){
  await fetch('/api/proposals/'+id+'/'+op, {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
  load();
}
load();
</script></body></html>"""
