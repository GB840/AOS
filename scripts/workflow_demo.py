"""工作流串联演示（Day15-21）：编排芯粒把多芯粒串成流水线。

本演示用三个合成芯粒（scan / fix / verify）模拟「代码审查」流水线：
  strix(扫描) -> atomcode(修复) -> mistralrs(验证)
其中 strix/atomcode/mistralrs 是独立开源项目，未来各写一个 fabric 适配器
(进程内或子进程) 即可真实接入；此处用合成芯粒证明「编排机制」本身成立，
且编排芯粒是用户态芯粒、复用枢纽路由层、不进内核。

用法（沙箱/主机均可，无需任何 API key）：
  python scripts/workflow_demo.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from kernel.plugins.fabric_hub import FabricHub


# ---- 合成芯粒：模拟「代码审查」流水线的三个环节 -------------------------
class _Scanner(BaseAgentAdapter):
    engine_id = "scanner"

    def advertise_capabilities(self):
        return ["code.scan"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        issues = ["unused_import", "null_deref"]
        return InvokeResult(ok=True, data={"issues": issues})


class _Fixer(BaseAgentAdapter):
    engine_id = "fixer"

    def advertise_capabilities(self):
        return ["code.fix"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        issues = req.payload.get("issues", [])
        return InvokeResult(ok=True, data={"fixed": issues, "patches": len(issues)})


class _Verifier(BaseAgentAdapter):
    engine_id = "verifier"

    def advertise_capabilities(self):
        return ["code.verify"]

    def health(self):
        return True

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        patches = req.payload.get("patches", 0)
        return InvokeResult(ok=True, data={"verified": patches, "status": "pass"})


def main() -> int:
    hub = FabricHub(adapters=(_Scanner, _Fixer, _Verifier))
    orch_id = hub.add_orchestrator()
    print("# AOS 工作流串联演示（编排芯粒 = 用户态，非内核）")
    print("# 流水线: scanner -> fixer -> verifier  (对应 strix->atomcode->mistralrs)")
    print("# 编排芯粒已注册为: %s" % orch_id)

    workflow = {
        "initial": {},
        "steps": [
            {"capability": "code.scan", "in": {}},
            {"capability": "code.fix", "in_from": "previous"},
            {"capability": "code.verify", "in_from": "previous"},
        ],
    }
    res = hub.route("system.workflow", workflow)
    if not res.ok:
        print("流水线失败: %s" % res.error)
        return 1
    print("流水线成功: %d 步" % res.data["ok_steps"])
    for t in res.data["trace"]:
        print("  step%d  %-12s -> %s" % (t["step"], t["capability"], t["out"]))
    print("最终结果: %s" % res.data["final"])
    print("\n结论: 编排芯粒经统一路由层把 3 个芯粒串成流水线，自身不入内核 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
