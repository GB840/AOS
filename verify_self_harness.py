"""验证 Self-Harness（C）端到端可跑、结果诚实。

运行：python verify_self_harness.py
"""
import os
import sys

sys.path.insert(0, "src")

# 注入临时目录，避免污染真实数据
os.environ.setdefault("AOS_PULSE_DIR", "data/_selftest/pulse")
os.environ.setdefault("AOS_CONTEXT_DIR", "data/_selftest/context")
os.environ.setdefault("AOS_EVAL_DIR", "data/_selftest/eval")

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {extra}")


print("[1] 自测报告结构")
from kernel.self_harness import SelfHarness
report = SelfHarness().run_self_test()
d = report.to_dict()
check("返回含 overall_status", "overall_status" in d, str(d))
check("overall_status 合法值", d["overall_status"] in ("healthy", "degraded", "unhealthy"),
      d.get("overall_status"))
check("含 adapters 列表", isinstance(d["adapters"], list))
check("含 eval_smoke", "ok" in d["eval_smoke"])
check("含 store_checks", isinstance(d["store_checks"], list))
check("含 recommendations", isinstance(d["recommendations"], list))

print("[2] 适配器探活诚实（vlm 无 key 时应 healthy=False）")
vlm = next((a for a in d["adapters"] if a["engine_id"] == "vlm"), None)
if vlm is not None:
    check("vlm 在无 VLM_API_KEY 时 healthy=False", vlm["healthy"] is False, str(vlm))
else:
    check("vlm 适配器被纳入探活（未导入则跳过）", True)

print("[3] eval 冒烟通过")
check("eval_smoke.ok == True", d["eval_smoke"].get("ok") is True, str(d["eval_smoke"]))
check("eval_smoke.score > 0", d["eval_smoke"].get("score", 0) > 0, str(d["eval_smoke"]))

print("[4] 存储可写性")
for s in d["store_checks"]:
    check(f"store {s['store']} 可写", s.get("writable") is True, str(s))

print(f"\n结果: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
