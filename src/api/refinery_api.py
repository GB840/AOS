"""代码炼化系统 API —— 将 Code Refinery API。

提供 REST 接口：
- POST /api/refinery/run         一键炼化项目
- POST /api/refinery/analyze    仅分析
- POST /api/refinery/tasks      任务列表
- GET  /api/refinery/tasks/{id}  任务详情
- POST /api/refinery/tasks/{id}/apply  应用优化
- POST /api/refinery/tasks/{id}/test   运行测试
- POST /api/refinery/tasks/{id}/rollback  回滚
- GET  /api/refinery/evolution/stats  进化系统统计
- GET  /api/refinery/evolution/patterns  蒸馏模式
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class RefineryRunRequest(BaseModel):
    project_root: str = Field(..., description="项目根目录（绝对路径）")
    description: str = Field("", description="任务描述")
    auto_apply: bool = Field(True, description="是否自动应用低风险优化")
    run_tests: bool = Field(True, description="是否运行测试验证")
    file_pattern: Optional[str] = Field(None, description="只分析匹配的文件")


class RefineryApplyRequest(BaseModel):
    proposal_ids: Optional[List[str]] = Field(None, description="要应用的提案 ID 列表，None 表示所有自动优化")


class RefineryTestRequest(BaseModel):
    test_dir: str = Field("tests", description="测试目录")


class RefineryRollbackRequest(BaseModel):
    snapshot_name: str = Field(..., description="快照名称或 ID")


# 单例引擎
_refinery_engine = None
_evolution_loop = None


def _get_refinery_engine():
    """懒加载炼化引擎。"""
    global _refinery_engine
    if _refinery_engine is None:
        from kernel.refinery import CodeRefineryEngine
        _refinery_engine = CodeRefineryEngine()
    return _refinery_engine


def _get_evolution_loop():
    """懒加载进化闭环。"""
    global _evolution_loop
    if _evolution_loop is None:
        from kernel.refinery import RefineryEvolutionLoop
        _evolution_loop = RefineryEvolutionLoop()
    return _evolution_loop


def mount_refinery_api(app: FastAPI) -> None:
    """把炼化 API 挂载到 FastAPI 应用。"""

    # ── 一键炼化 ──────────────────────────────────────────────
    @app.post("/api/refinery/run", tags=["refinery"])
    async def refinery_run(req: RefineryRunRequest):
        """一键炼化整个项目：分析 → 优化 → 测试 → 报告。"""
        try:
            engine = _get_refinery_engine()
            result = engine.refine_project(
                project_root=req.project_root,
                description=req.description,
                auto_apply=req.auto_apply,
                run_tests=req.run_tests,
            )

            # 记录进化
            if result.get("success") and result.get("report"):
                report = result["report"]
                try:
                    evo = _get_evolution_loop()
                    task = result.get("task", {})
                    proposals = []
                    if task.get("proposals"):
                        proposals = [
                            p for p in task["proposals"]
                            if p.get("id") in task.get("applied_proposals", [])
                        ]
                    evo.record_refinery_result(
                        task_id=task.get("id", ""),
                        project_root=req.project_root,
                        initial_score=report.get("initial_score", 0),
                        final_score=report.get("final_score", 0),
                        applied_proposals=proposals,
                        tests_passed=report.get("all_tests_pass", False),
                        duration_ms=report.get("duration_ms", 0),
                    )
                except Exception as e:
                    logger.warning("进化记录失败: %s", e)

            return result
        except Exception as e:
            logger.error("炼化失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 仅分析 ──────────────────────────────────────────────
    @app.post("/api/refinery/analyze", tags=["refinery"])
    async def refinery_analyze(req: RefineryRunRequest):
        """仅分析项目代码质量，不做修改。"""
        try:
            engine = _get_refinery_engine()
            task_result = engine.create_task(req.project_root, req.description)
            if not task_result.get("success"):
                raise HTTPException(status_code=500, detail=task_result.get("error"))

            task_id = task_result["task_id"]
            result = engine.analyze(task_id)
            return result
        except Exception as e:
            logger.error("分析失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 任务列表 ──────────────────────────────────────────
    @app.get("/api/refinery/tasks", tags=["refinery"])
    async def refinery_list_tasks():
        """列出所有炼化任务。"""
        try:
            engine = _get_refinery_engine()
            return {"success": True, "tasks": engine.list_tasks()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 任务详情 ──────────────────────────────────────────
    @app.get("/api/refinery/tasks/{task_id}", tags=["refinery"])
    async def refinery_get_task(task_id: str):
        """获取炼化任务详情。"""
        try:
            engine = _get_refinery_engine()
            task = engine.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
            return {"success": True, "task": task.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 应用优化 ──────────────────────────────────────────
    @app.post("/api/refinery/tasks/{task_id}/apply", tags=["refinery"])
    async def refinery_apply(task_id: str, req: RefineryApplyRequest):
        """对指定任务应用优化提案。"""
        try:
            engine = _get_refinery_engine()
            result = engine.apply_optimization(task_id, proposal_ids=req.proposal_ids)
            return result
        except Exception as e:
            logger.error("应用优化失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 运行测试 ──────────────────────────────────────────
    @app.post("/api/refinery/tasks/{task_id}/test", tags=["refinery"])
    async def refinery_test(task_id: str, req: RefineryTestRequest):
        """对指定任务运行测试。"""
        try:
            engine = _get_refinery_engine()
            result = engine.run_tests(task_id, test_dir=req.test_dir)
            return result
        except Exception as e:
            logger.error("测试失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 回滚 ──────────────────────────────────────────────
    @app.post("/api/refinery/tasks/{task_id}/rollback", tags=["refinery"])
    async def refinery_rollback(task_id: str, req: RefineryRollbackRequest):
        """回滚到指定快照。"""
        try:
            engine = _get_refinery_engine()
            result = engine.rollback(task_id, req.snapshot_name)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 完成任务 ──────────────────────────────────────────
    @app.post("/api/refinery/tasks/{task_id}/finalize", tags=["refinery"])
    async def refinery_finalize(task_id: str):
        """完成任务，生成最终报告。"""
        try:
            engine = _get_refinery_engine()
            result = engine.finalize(task_id)
            return result
        except Exception as e:
            logger.error("完成任务失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 进化系统统计 ──────────────────────────────────────
    @app.get("/api/refinery/evolution/stats", tags=["refinery-evolution"])
    async def refinery_evolution_stats():
        """获取进化系统统计数据。"""
        try:
            evo = _get_evolution_loop()
            return {"success": True, "stats": evo.stats()}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 蒸馏模式 ──────────────────────────────────────────
    @app.get("/api/refinery/evolution/patterns", tags=["refinery-evolution"])
    async def refinery_evolution_patterns(
        category: Optional[str] = Query(None, description="类别过滤"),
        min_confidence: float = Query(0.0, description="最小置信度"),
        auto_apply_only: bool = Query(False, description="仅推荐自动应用"),
    ):
        """获取蒸馏出的优化模式。"""
        try:
            evo = _get_evolution_loop()
            patterns = evo.get_patterns(
                category=category,
                min_confidence=min_confidence,
                auto_apply_only=auto_apply_only,
            )
            return {
                "success": True,
                "patterns": [p.to_dict() for p in patterns],
                "count": len(patterns),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 炼化建议 ──────────────────────────────────────────
    @app.get("/api/refinery/evolution/recommendations", tags=["refinery-evolution"])
    async def refinery_evolution_recommendations():
        """基于历史数据的炼化建议。"""
        try:
            evo = _get_evolution_loop()
            return evo.get_refinery_recommendations()
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── 增量分析 ──────────────────────────────────────────
    @app.post("/api/refinery/incremental", tags=["refinery"])
    async def refinery_incremental(req: RefineryRunRequest):
        """增量分析：只分析自上次以来变化的文件。"""
        try:
            from kernel.refinery import ProjectSandbox, IncrementalAnalyzer

            sb = ProjectSandbox(
                project_root=req.project_root,
                name=f"incr-{req.description[:20] or 'task'}",
                include_dirs=req.file_pattern.split(",") if req.file_pattern else None,
            )
            result = sb.create()
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=result.get("error"))

            try:
                inc = IncrementalAnalyzer(sb.root)
                inc_result = inc.analyze()
                return {
                    "success": True,
                    **inc_result.to_dict(),
                }
            finally:
                sb.destroy()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("增量分析失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # ── 多智能体团队炼化 ──────────────────────────────────
    @app.post("/api/refinery/team", tags=["refinery"])
    async def refinery_team_run(req: RefineryRunRequest):
        """多智能体团队炼化：架构师→工程师→审查员→执行者。"""
        try:
            from kernel.refinery import ProjectSandbox, CodeAnalyzer, RefineryTeam

            sb = ProjectSandbox(
                project_root=req.project_root,
                name=f"team-{req.description[:20] or 'task'}",
            )
            result = sb.create()
            if not result.get("success"):
                raise HTTPException(status_code=500, detail=result.get("error"))

            try:
                analyzer = CodeAnalyzer(sb.root)
                report = analyzer.analyze()
                team = RefineryTeam(sb.root)
                team_result = team.run(report.to_dict())
                return team_result
            finally:
                sb.destroy()
        except HTTPException:
            raise
        except Exception as e:
            logger.error("团队炼化失败: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    logger.info("代码炼化 API 已挂载: /api/refinery")
