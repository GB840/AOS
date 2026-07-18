"""Self-Harness API —— 暴露自测闭环端点（/api/self-harness/run）。

返回 SelfHarness 的结构化健康报告（JSON）。失败如实返回 error 字段。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI


def mount_self_harness_api(app: FastAPI) -> None:
    router = APIRouter(tags=["self-harness"])

    @router.get("/api/self-harness/run")
    def run_self_test() -> Any:
        """跑一轮自测，返回结构化健康报告。

        报告含：每适配器探活、eval 冒烟、存储可写性、总体状态、修复建议。
        """
        from kernel.self_harness import SelfHarness
        report = SelfHarness().run_self_test()
        return report.to_dict()

    app.include_router(router)
