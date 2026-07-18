"""步骤级审核封驳（④）端到端验证。

覆盖：
1. 闸门关闭（默认）→ 零回归：所有步骤照常执行，不建审批。
2. 闸门开启 + requires_approval → 敏感步被挡住(未执行)，建 pending 审批，run 状态 awaiting_review。
3. 准后 resume → 被挡步放行执行。
4. 驳回 → 封驳不执行、标记 rejected。
5. 审批 API（/api/approvals）经 TestClient 真实挂载：list/create/approve/reject。
6. 敏感能力集（code.exec 等）未标 requires_approval 也触发审核。

所有断言可复核；落盘均指向临时目录，不污染仓库。
"""
from __future__ import annotations
import os, sys, tempfile, shutil
from pathlib import Path

# —— 隔离落盘（必须在 import kernel 模块前设好 env）——
TMP = tempfile.mkdtemp(prefix="aos_review_")
os.environ["AOS_APPROVALS_PATH"] = os.path.join(TMP, "approvals.jsonl")
os.environ["AOS_RESUME_SPECS_PATH"] = os.path.join(TMP, "resume_specs.jsonl")
# 把 trace 落盘也重定向到临时目录，避免污染 src/_traces
import core.fabric.trace_store as _ts
_ts._traces_dir = lambda: Path(TMP)

from core.fabric.adapter import InvokeRequest, InvokeResult
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
from kernel.approval.review_gate import get_review_gate
from kernel.approval.approval_store import get_approval_store

passed = 0
failed = 0
def check(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {msg}")
    else:
        failed += 1
        print(f"  ✗ {msg}")

def make_route_fn(calls):
    """记录每次调用的假路由；bench.risky 返回 ok，bench.ping 返回 ok。"""
    def fn(cap, payload):
        calls.setdefault(cap, 0)
        calls[cap] += 1
        return InvokeResult(ok=True, data={"cap": cap, "echo": (payload or {}).get("text", "")})
    return fn

print("== 1. 闸门关闭（默认）→ 零回归 ==")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
spec = {"steps": [{"capability": "bench.ping", "in": {"text": "a"}},
                  {"capability": "bench.risky", "in": {"text": "b"}}]}
res = chip.invoke(InvokeRequest("workflow.execute", payload=spec))
check(res.ok, "run 成功")
check(calls.get("bench.ping") == 1 and calls.get("bench.risky") == 1, "两步骤均执行（无闸门拦截）")
store = get_approval_store()
check(len(store.list_all(source="orchestrator")) == 0, "未建任何 orchestrator 审批（零副作用）")

print("== 2. 闸门开启 + requires_approval → 挡住执行 ==")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
spec = {"review_mode": "gate", "task_id": "r2",
        "steps": [{"capability": "bench.ping", "in": {"text": "a"}},
                  {"capability": "bench.risky", "in": {"text": "b"}, "requires_approval": True}]}
res = chip.invoke(InvokeRequest("workflow.execute", payload=spec))
check(calls.get("bench.ping") == 1, "安全步照常执行")
check(calls.get("bench.risky", 0) == 0, "敏感步被挡住、未执行")
check(res.data.get("status") == "awaiting_review", f"run 状态=awaiting_review（实得 {res.data.get('status')}）")
pend = store.list_pending(source="orchestrator")
check(len(pend) == 1, "建了 1 条 pending 审批")
check(pend and pend[0].payload.get("step_index") == 1, "审批关联到 step_index=1")
# trace 落盘含 awaiting_review 状态
import json as _json
tr = _json.loads((Path(TMP) / "trace_r2.json").read_text(encoding="utf-8"))
await_step = [s for s in tr["steps"] if s.get("status") == "awaiting_review"]
check(len(await_step) == 1 and await_step[0]["capability"] == "bench.risky", "trace 文件标记 awaiting_review")

print("== 3. 准后 resume → 放行执行 ==")
store.approve(pend[0].id, decided_by="reviewer", note="同意")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
res = chip.invoke(InvokeRequest("workflow.execute", payload=spec))  # 同一 spec 重跑（resume 语义）
check(calls.get("bench.risky") == 1, "批准后敏感步执行（bench.risky 调用 1 次）")
# 注意：resume 重跑会从首步再跑（已知首版行为，安全前缀幂等）
check(calls.get("bench.ping") >= 1, "安全步在 resume 中重跑（预期）")

print("== 4. 驳回 → 封驳不执行 ==")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
spec4 = {"review_mode": "gate", "task_id": "r4",
         "steps": [{"capability": "bench.risky", "in": {"text": "x"}, "requires_approval": True}]}
chip.invoke(InvokeRequest("workflow.execute", payload=spec4))
pend4 = store.list_pending(source="orchestrator", risk_level="")
# 取 r4 的 pending
r4_pending = [a for a in store.list_all(source="orchestrator") if a.run_id == "r4" and a.status == "pending"]
check(len(r4_pending) == 1, "r4 建了 pending 审批")
store.reject(r4_pending[0].id, decided_by="reviewer", note="不安全")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
res4 = chip.invoke(InvokeRequest("workflow.execute", payload=spec4))
check(calls.get("bench.risky", 0) == 0, "驳回后敏感步仍不执行（封驳生效）")
check(any(s.get("status") == "rejected" for s in res4.data.get("trace", [])), "trace 标记 rejected")

print("== 5. 敏感能力集自动触发（未标 requires_approval）==")
calls = {}
chip = OrchestrationChiplet(make_route_fn(calls))
spec5 = {"review_mode": "gate", "task_id": "r5",
         "steps": [{"capability": "code.exec", "in": {"text": "rm -rf"}}]}
chip.invoke(InvokeRequest("workflow.execute", payload=spec5))
r5_pending = [a for a in store.list_all(source="orchestrator") if a.run_id == "r5" and a.status == "pending"]
check(len(r5_pending) == 1, "code.exec 命中敏感能力集，自动进审核（无需显式标 requires_approval）")
check(calls.get("code.exec", 0) == 0, "敏感能力未批准前不执行")

print("== 6. 审批 API（TestClient 真实挂载）==")
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.approval_api import mount_approval_api
app = FastAPI()
mount_approval_api(app)
client = TestClient(app)
# 注：approval 单例已缓存在 TMP/approvals.jsonl，API 测试复用同一 store（含前序测试审批）
r = client.post("/api/approvals", json={"source": "evolve", "title": "测试提案", "risk_level": "high"})
check(r.status_code == 200 and r.json().get("status") == "ok", "POST /api/approvals 建审批成功")
aid = r.json()["approval"]["id"]
r = client.get("/api/approvals?status=pending")
check(r.status_code == 200 and r.json().get("total", 0) >= 1, "GET /api/approvals?status=pending 列出待审")
r = client.post(f"/api/approvals/{aid}/approve", json={"decided_by": "reviewer"})
check(r.status_code == 200 and r.json().get("approval", {}).get("status") == "approved", "POST approve 批准成功")
r = client.post(f"/api/approvals/{aid}/approve", json={})
check(r.status_code == 400, "重复批准被拒（已决策状态不可再批）")
r = client.get(f"/api/approvals/stats")
check(r.status_code == 200 and r.json().get("stats", {}).get("approved", 0) >= 1, "stats 反映已批准计数")

print(f"\n结果：通过 {passed} / 失败 {failed}")
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if failed else 0)
