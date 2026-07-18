"""看板 API 真跑验证（任务①）。

- 用临时目录隔离（monkeypatch _traces_dir），绝不碰生产 src/_traces，不留假数据
- 用 TestClient 验 /api/kanban/runs 列表归一化 + /api/kanban/runs/{id} 详情
- 验不存在 run 返回 404
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "src")

from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.kanban_api as kapi

PASS = 0
FAIL = 0


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


def main():
    tmp = Path(tempfile.mkdtemp()) / "_traces"
    tmp.mkdir(parents=True, exist_ok=True)
    kapi._traces_dir = lambda: tmp  # 隔离：验证读写都在临时目录

    trace = {
        "task_id": "t1",
        "input": {"task": "测试目标：检索并总结"},
        "steps": [
            {"capability": "web.search", "engine": "anysearch", "ok": True, "latency_ms": 12.3},
            {"capability": "llm.chat", "engine": "deepseek", "ok": False, "error": "boom"},
        ],
        "metrics": {"latency_ms": 12.3},
        "ts": "2026-07-19T00:00:00Z",
        "ok": False,
    }
    p = tmp / "trace_t1.json"
    p.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")

    app = FastAPI()
    kapi.mount_kanban_api(app)
    c = TestClient(app)

    r = c.get("/api/kanban/runs")
    check(r.status_code == 200, f"列表接口 200 (got {r.status_code})")
    data = r.json()
    check(data["status"] == "ok", "列表 status=ok")
    items = [i for i in data["items"] if i["run_id"] == "t1"]
    check(len(items) == 1, "trace_t1 出现在列表")
    item = items[0]
    check(item["goal"] == "测试目标：检索并总结", "goal 解析正确")
    check(item["status"] == "partial", "状态判定为 partial（1 成 1 败）")
    check(item["ok_steps"] == 1 and item["failed_steps"] == 1, "ok/failed 步计数正确")
    check(item["total_latency_ms"] == 12.3, "总延迟累加正确")
    check(item["steps"][1]["ok"] is False and item["steps"][1]["error"] == "boom", "失败步含 error")

    r2 = c.get("/api/kanban/runs/t1")
    check(r2.status_code == 200, f"详情接口 200 (got {r2.status_code})")
    check(r2.json()["run"]["status"] == "partial", "详情状态一致")

    r3 = c.get("/api/kanban/runs/nope")
    check(r3.status_code == 404, f"不存在 run 返回 404 (got {r3.status_code})")

    print(f"\n看板验证: {PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
