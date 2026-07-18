"""验证多模态（D / VLMAdapter）能力声明与诚实降级。

运行：python verify_multimodal.py
"""
import os
import sys

sys.path.insert(0, "src")

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


print("[1] 能力声明")
from core.fabric.adapters.vlm_adapter import VLMAdapter
from core.fabric.capability import Capability
ad = VLMAdapter()
caps = ad.advertise_capabilities()
check("声明 VISION_UNDERSTAND", Capability.VISION_UNDERSTAND in caps, str(caps))

print("[2] health 诚实（无 VLM_API_KEY 时 False）")
check("无 key 时 health()==False", ad.health() is False)

print("[3] health_detail 结构")
hd = ad.health_detail()
check("health_detail 含 engine=vlm", hd.get("engine") == "vlm")
check("health_detail 含 ready", "ready" in hd)
check("无后端时 ready=False", hd.get("ready") is False)

print("[4] invoke 无后端诚实返回 ok=False（不伪造）")
from core.fabric.adapter import InvokeRequest
res = ad.invoke(InvokeRequest(
    capability=Capability.VISION_UNDERSTAND,
    payload={"image_path": "nope.png", "prompt": "描述这张图"},
))
check("无后端 invoke ok=False", res.ok is False)
check("error 非空（诚实原因）", bool(res.error), str(res.error))

print("[5] API 端点（TestClient）")
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.vlm_api import mount_vlm_api
    app = FastAPI()
    mount_vlm_api(app)
    client = TestClient(app)
    r = client.get("/api/multimodal/health")
    check("GET /api/multimodal/health 200", r.status_code == 200)
    check("health 返回 ready 字段", "ready" in r.json())
    r2 = client.post("/api/multimodal/analyze",
                     json={"image_path": "nope.png", "prompt": "x"})
    check("POST /api/multimodal/analyze 返回 ok=False（无后端诚实）",
          r2.status_code == 200 and r2.json().get("ok") is False, str(r2.json()))
except Exception as e:  # noqa: BLE001
    check(f"API 测试异常: {e}", False, str(e))

print(f"\n结果: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
