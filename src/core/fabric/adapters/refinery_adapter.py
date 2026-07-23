"""代码炼化 FabricHub 适配器（Refinery Adapter）。

把炼化系统注册为 FabricHub 的一个能力供给方，使其他组件可以经
`hub.route(Capability.CODE_REFINE, {...})` 统一调用炼化服务。

支持的操作（payload["action"]）：
- "analyze"   : 分析指定项目目录，返回质量报告
- "refine"    : 一键炼化（分析→优化→测试→报告）
- "patterns"  : 查询进化蒸馏模式
- "stats"     : 查询进化统计

遵循 AOS 全局约定：
- 实现 BaseAgentAdapter 四方法契约
- health() 做真实通电自检（不硬编码 True）
- 经 FabricHub 统一路由，不绕过 hub
"""

from __future__ import annotations

import logging
from typing import Any

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)


class RefineryAdapter(BaseAgentAdapter):
    """代码炼化适配器：把 RefineryEngine 接入 FabricHub 能力路由。

    经 hub.route(Capability.CODE_REFINE, {"action": "refine", "project_root": "..."})
    即可触发炼化流程，与其他能力（搜索、记忆、代码生成等）无缝编排。
    """

    def __init__(self):
        self._engine = None
        self._evolution = None

    @property
    def engine_id(self) -> str:
        return "refinery"

    def advertise_capabilities(self) -> list[Capability]:
        """声明炼化引擎提供的能力。"""
        return [Capability.CODE_REFINE, Capability.SECURITY_AUDIT]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        """执行炼化能力调用。

        Args:
            req.capability: CODE_REFINE 或 SECURITY_AUDIT
            req.payload: {"action": "analyze|refine|patterns|stats", ...}
        """
        try:
            action = req.payload.get("action", "")
            cap = req.capability

            if cap == Capability.SECURITY_AUDIT:
                return self._do_analyze(req.payload)
            if cap == Capability.CODE_REFINE:
                if action == "analyze":
                    return self._do_analyze(req.payload)
                elif action == "refine":
                    return self._do_refine(req.payload)
                elif action == "patterns":
                    return self._do_patterns(req.payload)
                elif action == "stats":
                    return self._do_stats()
                else:
                    return InvokeResult(
                        ok=False,
                        error=f"未知 action: {action}（支持: analyze/refine/patterns/stats）",
                    )
            return InvokeResult(ok=False, error=f"不支持的能力: {cap}")
        except Exception as e:
            logger.error("炼化适配器调用失败: %s", e, exc_info=True)
            return InvokeResult(ok=False, error=repr(e))

    def health(self) -> bool:
        """通电自检：确认炼化核心模块可导入。"""
        try:
            from kernel.refinery.code_analyzer import CodeAnalyzer  # noqa: F401
            from kernel.refinery.project_sandbox import ProjectSandbox  # noqa: F401
            from kernel.refinery.refinery_engine import CodeRefineryEngine  # noqa: F401
            return True
        except Exception:
            return False

    def tier(self) -> str:
        return TIER_HIGH

    # ── 各操作实现 ──────────────────────────────────────────────────

    def _do_analyze(self, payload: dict[str, Any]) -> InvokeResult:
        """分析项目代码质量。"""
        project_root = payload.get("project_root")
        if not project_root:
            return InvokeResult(ok=False, error="缺少 project_root 参数")

        from kernel.refinery.project_sandbox import ProjectSandbox
        from kernel.refinery.code_analyzer import CodeAnalyzer

        sb = ProjectSandbox(
            project_root=project_root,
            name="fabric-analyze",
            include_dirs=payload.get("include_dirs"),
        )
        result = sb.create()
        if not result.get("success"):
            return InvokeResult(ok=False, error=result.get("error", "沙箱创建失败"))

        try:
            analyzer = CodeAnalyzer(sb.root)
            report = analyzer.analyze()
            return InvokeResult(
                ok=True,
                data={
                    "report": report.to_dict(),
                    "sandbox_files": result.get("file_count", 0),
                },
                engine_id=self.engine_id,
            )
        finally:
            sb.destroy()

    def _do_refine(self, payload: dict[str, Any]) -> InvokeResult:
        """一键炼化。"""
        project_root = payload.get("project_root")
        if not project_root:
            return InvokeResult(ok=False, error="缺少 project_root 参数")

        engine = self._get_engine()
        result = engine.refine_project(
            project_root=project_root,
            description=payload.get("description", ""),
            auto_apply=payload.get("auto_apply", True),
            run_tests=payload.get("run_tests", True),
        )
        return InvokeResult(
            ok=result.get("success", False),
            data=result,
            error=result.get("error"),
            engine_id=self.engine_id,
        )

    def _do_patterns(self, payload: dict[str, Any]) -> InvokeResult:
        """查询进化蒸馏模式。"""
        evo = self._get_evolution()
        patterns = evo.get_patterns(
            auto_apply_only=payload.get("auto_apply_only", False)
        )
        return InvokeResult(
            ok=True,
            data={"patterns": [p.to_dict() for p in patterns],
                  "count": len(patterns)},
            engine_id=self.engine_id,
        )

    def _do_stats(self) -> InvokeResult:
        """查询进化统计。"""
        evo = self._get_evolution()
        stats = evo.get_stats()
        return InvokeResult(
            ok=True,
            data=stats,
            engine_id=self.engine_id,
        )

    # ── 懒加载 ──────────────────────────────────────────────────────

    def _get_engine(self):
        if self._engine is None:
            from kernel.refinery.refinery_engine import CodeRefineryEngine
            self._engine = CodeRefineryEngine()
        return self._engine

    def _get_evolution(self):
        if self._evolution is None:
            from kernel.refinery.evolution_loop import RefineryEvolutionLoop
            self._evolution = RefineryEvolutionLoop()
        return self._evolution
