import asyncio
import json
import sys
import time

import httpx
from api.main import app  # 导入即挂载全部路由（含单创OS）

BASE = "http://testserver"
UID = int(time.time())


async def main():
    # ASGITransport 不跑 lifespan，直接打应用本体（代码路径与真实 HTTP 服务完全一致）
    transport = httpx.ASGITransport(app=app)
    results = {}
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as client:
        # 1. 健康
        r = await client.get("/health")
        results["health_200"] = (r.status_code == 200)
        # 2. openapi（曾 500）——强制完整 schema 解析
        r = await client.get("/openapi.json")
        results["openapi_200"] = (r.status_code == 200)
        if r.status_code == 200:
            spec = r.json()
            results["routes"] = len(spec.get("paths", {}))
            results["schemas"] = len(spec.get("components", {}).get("schemas", {}))
            # 关键：danchuang 的 POST 模型必须在 schema 中且为 body 而非 query
            paths = spec.get("paths", {})
            reg = paths.get("/api/danchuang/tenant/register", {})
            post = reg.get("post", {})
            req_body = post.get("requestBody")
            params = post.get("parameters", [])
            query_like = [p for p in params if p.get("in") == "query"]
            results["register_has_requestbody"] = req_body is not None
            results["register_no_query_params"] = (len(query_like) == 0)
        # 3. 注册租户（POST，曾 422）——用唯一名避免重复冲突
        r = await client.post("/api/danchuang/tenant/register",
                              json={"name": f"verify_{UID}", "email": f"verify_{UID}@example.com"})
        results["tenant_register_200"] = (r.status_code == 200)
        api_key = None
        if r.status_code == 200:
            api_key = r.json().get("api_key")
        results["got_api_key"] = bool(api_key)
        # 4. 租户 key 调 status
        if api_key:
            r = await client.get("/api/danchuang/status", headers={"X-API-Key": api_key})
            results["status_with_tenant_key_200"] = (r.status_code == 200)
            # 5. 设目标
            r = await client.post("/api/danchuang/goal/set",
                                  json={"goal": "验证端到端链路通顺", "horizon_days": 7},
                                  headers={"X-API-Key": api_key})
            results["goal_set_200"] = (r.status_code == 200)
            # 6. 回读 has_goal
            r = await client.get("/api/danchuang/status", headers={"X-API-Key": api_key})
            if r.status_code == 200:
                results["has_goal"] = r.json().get("has_goal") is True
            # 7. 伪造 key 应拒
            r = await client.get("/api/danchuang/status", headers={"X-API-Key": "sk-fake-0000"})
            results["fake_key_rejected"] = (r.status_code in (401, 403))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    ok = all(v for k, v in results.items() if k not in ("routes", "schemas"))
    print("ALL_PASS" if ok else "SOME_FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
