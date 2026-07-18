"""可干预记忆控制面 真跑验证（任务②）。

两层验证：
1. MemoryControlStore 单元（临时文件，隔离生产）：add→list(scope/project 过滤)
   →update(edit_history 快照)→rollback(恢复到 v1)→get→delete(软删)→list 排除→rollback 已删返回 None
2. HTTP API 层（注入临时 store，隔离默认路径）：POST add / GET / PATCH update /
   POST rollback / DELETE / 404 不存在
"""
from __future__ import annotations
import os
import sys
import tempfile

sys.path.insert(0, "src")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from kernel.memory_control import MemoryControlStore
import api.memory_control_api as mcapi

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


def test_store():
    print("── MemoryControlStore 单元 ──")
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "controllable_memory.jsonl")
    s = MemoryControlStore(path=p)

    rec = s.add("初始文本", "user_note", scope="project", project_id="P1")
    mid = rec["id"]
    check(rec["version"] == 1 and rec["scope"] == "project", "add 生成 v1 + scope=project")
    check(len(s.list(scope="project", project_id="P1")) == 1, "list 按 scope+project 过滤命中")
    check(len(s.list(scope="global")) == 0, "list scope=global 不命中")

    rec2 = s.update(mid, text="改后文本")
    check(rec2["version"] == 2 and rec2["text"] == "改后文本", "update 升到 v2 且文本变更")
    check(len(rec2["edit_history"]) == 1, "edit_history 记录 1 条")
    check(rec2["edit_history"][0]["snapshot"]["text"] == "初始文本", "快照保留旧文本")

    rec3 = s.rollback(mid, version=1)
    check(rec3["text"] == "初始文本" and rec3["version"] == 3, "rollback 恢复到 v1 文本且升 v3")
    check(rec3["edit_history"][-1]["action"] == "rollback_to", "edit_history 记 rollback_to")

    check(s.get(mid)["text"] == "初始文本", "get 取回回滚后文本")

    check(s.delete(mid) is True, "delete 软删成功")
    check(s.get(mid)["deleted"] is True, "get 仍可取（含 deleted 标记）")
    check(len(s.list()) == 0, "list 排除软删项")
    check(s.rollback(mid, 1) is None, "已删项 rollback 返回 None（诚实）")


def test_api():
    print("── HTTP API 层 ──")
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "controllable_memory.jsonl")
    mcapi._store = MemoryControlStore(path=p)  # 注入隔离 store
    app = FastAPI()
    mcapi.mount_memory_control_api(app)
    c = TestClient(app)

    r = c.post("/api/memory/control", json={"text": "API文本", "category": "user_note", "scope": "project", "project_id": "P2"})
    check(r.status_code == 200, f"POST add 200 (got {r.status_code})")
    mid = r.json()["memory"]["id"]

    r = c.get(f"/api/memory/control/{mid}")
    check(r.status_code == 200 and r.json()["memory"]["text"] == "API文本", "GET 取回")

    r = c.patch(f"/api/memory/control/{mid}", json={"text": "API改后"})
    check(r.status_code == 200 and r.json()["memory"]["text"] == "API改后", "PATCH update 生效")

    r = c.post(f"/api/memory/control/{mid}/rollback", json={"version": 1})
    check(r.status_code == 200 and r.json()["memory"]["text"] == "API文本", "POST rollback 恢复 v1")

    r = c.delete(f"/api/memory/control/{mid}")
    check(r.status_code == 200 and r.json()["deleted"] is True, "DELETE 软删")

    r = c.get(f"/api/memory/control/{mid}")
    check(r.status_code == 404, f"已删 GET 返回 404 (got {r.status_code})")


def main():
    test_store()
    test_api()
    print(f"\n记忆控制面验证: {PASS} 通过 / {FAIL} 失败")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
