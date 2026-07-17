"""code_team 的 FabricHub 适配器 —— 把「多智能体代码团队」作为可路由引擎接进
AOS 能力路由枢纽。

这是 code_team「建好未接电」的最后一块拼图：此前 code_team 只是 3 个独立 API
端点 + 一个模块，既不是 FabricHub 引擎、也没能力、不在路由/健康/预测器里——
是座孤岛。本适配器让它经 ``hub.route("code.generate", ...)`` 可达、出现在
health_report 的 live 列表、真实流量喂给路由预测器、并享受引擎透明化
（engine_id="code-team"）。

设计（与现有芯粒一致）：
  - health() 恒 True：heuristic 模式永远可离线跑；真实 LLM 不可用时回落
    heuristic，不会標 dead。具体某次请求的成败由 invoke() 的 ok 反映，喂预测器。
  - invoke() 把 payload{requirement,lang} 转成 CodeTeamOrchestrator.run()，
    结果整体塞进 InvokeResult.data（保持 code_team 既有的结构化结果形状，
    调用方零改造）。
  - 真实 LLM（AOS_CODETEAM_LLM=1）走 make_llm_generate() 复用推理平面；
    未开则 heuristic 脚手架。两种路径都对调用方透明。
"""
from __future__ import annotations

from typing import Any

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability, ENGINE_TIER, TIER_HIGH

from .code_team import CodeTeamOrchestrator, make_llm_generate


class CodeTeamAdapter(BaseAgentAdapter):
    """FabricHub 引擎：自然语言需求 → 多文件代码（架构/编码/质量门/真实测试）。"""

    @property
    def engine_id(self) -> str:
        return "code-team"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CODE_GENERATE]

    def health(self) -> bool:
        # heuristic 模式零依赖永远可跑；真实 LLM 不可用时回落 heuristic，不標 dead。
        # 具体某次请求的成败由 invoke() 的 ok 反映，喂给路由预测器（诚实不编）。
        return True

    def tier(self) -> str:
        return ENGINE_TIER.get(self.engine_id, TIER_HIGH)

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        requirement = payload.get("requirement", "")
        lang = payload.get("lang", "python")
        try:
            llm = make_llm_generate()
            result = CodeTeamOrchestrator(llm_generate=llm).run(requirement, lang=lang)
            result["llm_used"] = llm is not None
            exec_err = (result.get("execution") or {}).get("error")
            return InvokeResult(
                ok=bool(result.get("ok", False)),
                data=result,
                error=None if result.get("ok") else exec_err,
                engine_id=self.engine_id,
            )
        except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
            return InvokeResult(
                ok=False,
                error=f"code_team invoke failed: {type(e).__name__}: {e}",
                engine_id=self.engine_id,
            )


__all__ = ["CodeTeamAdapter"]
