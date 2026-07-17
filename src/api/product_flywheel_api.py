"""产品飞轮 API —— Studio / Hub / Pulse / Evolve 的 HTTP 接口。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
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


# ═══════════════════════════════════════════
#  挂载所有 router
# ═══════════════════════════════════════════

def mount_product_flywheel(app):
    """把产品飞轮的 API 挂载到 FastAPI app 上。"""
    app.include_router(router)
    app.include_router(hub_router)
    app.include_router(pulse_router)
    app.include_router(evolve_router)
    logger.info("产品飞轮 API 已挂载: /api/studio, /api/hub, /api/pulse, /api/evolve")
