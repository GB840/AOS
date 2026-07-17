"""AutoSkill API —— 全自动技能发现与使用的 HTTP 接口。

核心：用户说一句话，系统全自动搞定——找技能、装技能、用技能。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autoskill", tags=["autoskill"])


# ── Pydantic 模型 ──

class RunAutoRequest(BaseModel):
    task: str
    auto_install: bool = True
    confirm_risk_level: str = "low"  # low/medium/high


class InstallSkillRequest(BaseModel):
    skill_id: str


class SearchSkillRequest(BaseModel):
    query: str
    limit: int = 10


# ── 工具函数 ──

def _get_agent():
    """获取 AutoSkill Agent。"""
    try:
        from skills.autoskill_agent import get_autoskill_agent
        agent = get_autoskill_agent()

        # 尝试注入 hub
        try:
            from kernel.plugins.fabric_hub import get_fabric_hub
            hub = get_fabric_hub()
            agent.set_hub(hub)
            # 注入 route_fn
            agent.set_route_fn(hub.route)
        except Exception:
            pass

        return agent
    except Exception as e:
        logger.error("初始化 AutoSkill Agent 失败: %s", e)
        raise HTTPException(status_code=500, detail=f"AutoSkill 初始化失败: {e}")


# ── 核心接口 ──

@router.post("/run")
async def auto_run(req: RunAutoRequest, request: Request):
    """全自动：一句话 → 自动找技能 → 自动装 → 自动跑 → 返回结果。

    这是 AutoSkill 的核心入口。用户说一句话，剩下的全自动化。
    """
    if not req.task:
        raise HTTPException(status_code=400, detail="task 不能为空")

    agent = _get_agent()

    def _do_run():
        result = agent.run(
            task=req.task,
            auto_install=req.auto_install,
            confirm_risk_level=req.confirm_risk_level,
        )
        return {
            "ok": result.ok,
            "task": result.task,
            "steps": result.steps,
            "final_output": _serialize(result.final_output),
            "error": result.error,
            "skills_used": result.skills_used,
            "skills_installed": result.skills_installed,
            "duration_seconds": result.duration,
        }

    try:
        result = await asyncio.to_thread(_do_run)
        return result
    except Exception as e:
        logger.error("AutoSkill 执行失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze")
async def analyze_task(req: RunAutoRequest, request: Request):
    """只分析任务需要的能力，不执行。"""
    if not req.task:
        raise HTTPException(status_code=400, detail="task 不能为空")

    agent = _get_agent()

    def _do_analyze():
        capabilities = agent._analyze_task(req.task)
        local_caps = agent._check_local_capabilities(capabilities)
        missing = [c for c in capabilities if c not in local_caps]
        return {
            "task": req.task,
            "capabilities_needed": capabilities,
            "local_available": local_caps,
            "missing_capabilities": missing,
        }

    try:
        return await asyncio.to_thread(_do_analyze)
    except Exception as e:
        logger.error("任务分析失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ── 技能管理 ──

@router.get("/skills")
async def list_installed_skills(request: Request):
    """列出已安装的技能。"""
    try:
        from skills.autoskill_engine import get_autoskill_engine
        engine = get_autoskill_engine()
        return {"skills": engine.list_installed(), "count": len(engine.list_installed())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/skills/install")
async def install_skill(req: InstallSkillRequest, request: Request):
    """安装一个技能。"""
    try:
        from skills.autoskill_engine import get_autoskill_engine
        engine = get_autoskill_engine()
        result = engine.install(req.skill_id)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result.get("message", "安装失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/skills/{skill_id}")
async def uninstall_skill(skill_id: str, request: Request):
    """卸载一个技能。"""
    try:
        from skills.autoskill_engine import get_autoskill_engine
        engine = get_autoskill_engine()
        ok = engine.uninstall(skill_id)
        if not ok:
            raise HTTPException(status_code=404, detail="技能不存在")
        return {"ok": True, "skill_id": skill_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── SkillHub 搜索 ──

@router.post("/search")
async def search_skills(req: SearchSkillRequest, request: Request):
    """在 SkillHub 搜索技能。"""
    try:
        from skills.skillhub_integration import get_skillhub_adapter
        adapter = get_skillhub_adapter()
        if not adapter.available:
            raise HTTPException(status_code=503, detail="SkillHub 不可用")

        results = adapter.search(req.query, limit=req.limit)
        return {"query": req.query, "results": results, "count": len(results)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def autoskill_status(request: Request):
    """AutoSkill 状态检查。"""
    try:
        from skills.autoskill_engine import get_autoskill_engine
        from skills.skillhub_integration import skillhub_available
        from skills.autoskill_agent import get_autoskill_agent

        engine = get_autoskill_engine()
        agent = get_autoskill_agent()

        return {
            "autoskill_enabled": True,
            "skillhub_available": skillhub_available(),
            "installed_skills_count": len(engine.list_installed()),
            "agent_available": agent is not None,
            "auto_install_default": True,
            "risk_confirmation_threshold": "low",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 工具函数 ──

def _serialize(obj: Any) -> Any:
    """序列化结果，处理不可 JSON 序列化的对象。"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool, list, dict)):
        return obj
    # 尝试用 dataclasses
    try:
        from dataclasses import asdict, is_dataclass
        if is_dataclass(obj):
            return asdict(obj)
    except Exception:
        pass
    # 尝试 __dict__
    try:
        if hasattr(obj, "__dict__"):
            return obj.__dict__
    except Exception:
        pass
    # 兜底
    return str(obj)
