"""Task 2: Context Engineering —— 端到端验证脚本。

验证范围（共 40 项）：
1. ContextManager 基础：创建/添加/查询/统计
2. 优先级机制：CRITICAL/HIGH/NORMAL/LOW
3. 自动压缩：超阈值触发、保留最近 N 步、合并摘要
4. 跨会话持久化：persist/load
5. 全局会话注册表：get_session/list/delete
6. OrchestrationChiplet 集成：spec.context_session_id 触发上下文记录
7. WorkflowRunner 集成：context_session_id 参数触发上下文记录
8. API 端点：/api/context/* CRUD
9. 优雅降级：ContextManager 不可用时不影响主流程
10. 既有行为兼容：不传 context_session_id 时行为不变

运行：
    python verify_context_engineering.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# 设置 PYTHONPATH
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

# 用临时目录隔离测试数据，避免污染真实 workspace
_tmp = tempfile.mkdtemp(prefix="aos_ctx_test_")
os.environ["AOS_CONTEXT_DIR"] = os.path.join(_tmp, "context")

PASS = 0
FAIL = 0
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  ✗ {name}  {detail}")


# ═══════════════════════════════════════════════════════════════
# 1. ContextManager 基础
# ═══════════════════════════════════════════════════════════════

def test_context_manager_basics():
    print("\n[1] ContextManager 基础")
    from kernel.context.context_manager import (
        ContextManager, PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL,
    )

    # 创建空会话
    cm = ContextManager(session_id="test_basic", max_tokens=8000)
    check("创建空会话", cm.session_id == "test_basic")
    check("初始 entries 为空", len(cm._entries) == 0)
    check("初始 total_tokens=0", cm.total_tokens() == 0)

    # 添加一个成功步骤
    entry1 = cm.add_step({
        "step_index": 0,
        "step_name": "search",
        "capability": "web.search",
        "ok": True,
        "error": "",
        "output": {"content": "找到了 Python 3.13 的新特性"},
    })
    check("添加成功步骤返回 entry", entry1 is not None)
    check("entry 内容被填充", "Python 3.13" in entry1.content)
    check("entry token_count > 0", entry1.token_count > 0)
    check("entry 默认 priority=NORMAL 或 HIGH",
          entry1.priority in (PRIORITY_NORMAL, PRIORITY_HIGH))

    # 添加一个失败步骤
    entry2 = cm.add_step({
        "step_index": 1,
        "step_name": "fetch",
        "capability": "web.fetch",
        "ok": False,
        "error": "404 Not Found",
        "output": {},
    })
    check("失败步骤 priority=CRITICAL", entry2.priority == PRIORITY_CRITICAL)
    check("失败步骤 error 被记录", "404" in entry2.error)

    # 添加一段消息
    msg = cm.add_message("assistant", "这是 LLM 的回复", priority=PRIORITY_NORMAL)
    check("添加消息返回 entry", msg is not None)
    check("消息 capability=inference.llm", msg.capability == "inference.llm")

    # 统计
    stats = cm.stats()
    check("stats 返回 total_entries=3", stats["total_entries"] == 3, f"got {stats['total_entries']}")
    check("stats 返回 total_tokens > 0", stats["total_tokens"] > 0)
    check("stats 返回 by_priority 字典", isinstance(stats["by_priority"], dict))
    check("stats 返回 token_usage_pct", "token_usage_pct" in stats)

    # 查询
    all_entries = cm.get_entries()
    check("get_entries 返回全部 3 条", len(all_entries) == 3)
    critical_entries = cm.get_entries(priority=PRIORITY_CRITICAL)
    check("get_entries(priority=critical) 返回 1 条", len(critical_entries) == 1)

    # 上下文文本
    text = cm.get_context_text()
    check("get_context_text 非空", len(text) > 0)
    check("get_context_text 包含步骤内容", "Python 3.13" in text)
    check("get_context_text 包含错误信息", "404" in text)


# ═══════════════════════════════════════════════════════════════
# 2. 优先级机制
# ═══════════════════════════════════════════════════════════════

def test_priority_mechanism():
    print("\n[2] 优先级机制")
    from kernel.context.context_manager import (
        ContextManager, PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_NORMAL,
    )

    cm = ContextManager(session_id="test_prio", max_tokens=100000,
                        preserve_recent=3, auto_compact=False)

    # 添加 5 个步骤
    for i in range(5):
        cm.add_step({
            "step_index": i,
            "step_name": f"step_{i}",
            "capability": "bench.ping",
            "ok": True,
            "output": {"content": f"output {i}" * 10},
        })

    # 最近 3 步应该是 HIGH
    entries = cm.get_entries()
    high_count = sum(1 for e in entries if e["priority"] == PRIORITY_HIGH)
    check("最近 3 步为 HIGH（preserve_recent=3）", high_count == 3,
          f"got {high_count}")

    # 前 2 步是 NORMAL
    normal_count = sum(1 for e in entries if e["priority"] == PRIORITY_NORMAL)
    check("非最近步骤为 NORMAL", normal_count == 2, f"got {normal_count}")

    # 添加一个失败步骤，应是 CRITICAL
    cm.add_step({
        "step_index": 5,
        "step_name": "fail_step",
        "capability": "bench.fail",
        "ok": False,
        "error": "boom",
        "output": {},
    })
    entries = cm.get_entries()
    critical_entries = [e for e in entries if e["priority"] == PRIORITY_CRITICAL]
    check("失败步骤为 CRITICAL", len(critical_entries) == 1)


# ═══════════════════════════════════════════════════════════════
# 3. 自动压缩
# ═══════════════════════════════════════════════════════════════

def test_compaction():
    print("\n[3] 自动压缩")
    from kernel.context.context_manager import ContextManager, PRIORITY_LOW

    # 用很小的 max_tokens 触发压缩
    cm = ContextManager(session_id="test_compact", max_tokens=200,
                        preserve_recent=2, auto_compact=False)

    # 添加 10 个步骤，每个内容较大
    for i in range(10):
        cm.add_step({
            "step_index": i,
            "step_name": f"step_{i}",
            "capability": "bench.ping",
            "ok": True,
            "output": {"content": f"这是第 {i} 步的输出内容，重复多次以增加 token 数量。 " * 20},
        })

    # 原始未压缩的总 token（在 auto_compact=False 下）
    stats_before = cm.stats()
    check("auto_compact=False 时无压缩", stats_before["compacted_count"] == 0)

    # 手动触发压缩
    result = cm.compact_if_needed()
    check("手动压缩触发成功", result["compacted"] is True, f"got {result}")
    check("压缩前 token > 压缩后 token",
          result["before_tokens"] > result["after_tokens"],
          f"before={result['before_tokens']} after={result['after_tokens']}")
    check("压缩至少省 50% token",
          result["after_tokens"] < result["before_tokens"] * 0.5,
          f"before={result['before_tokens']} after={result['after_tokens']}")

    stats = cm.stats()
    check("至少有 1 个压缩条目", stats["compacted_count"] >= 1,
          f"compacted_count={stats['compacted_count']}")

    # 验证最近 2 步未被压缩
    entries = cm.get_entries()
    recent_2 = entries[-2:]
    for e in recent_2:
        check(f"步骤 {e['step_index']} 未被压缩（最近）",
              not e["compacted"], f"step {e['step_index']} was compacted")

    # 验证有 LOW 优先级的摘要条目
    low_entries = [e for e in entries if e["priority"] == PRIORITY_LOW]
    check("存在 LOW 优先级摘要条目", len(low_entries) >= 1,
          f"got {len(low_entries)}")

    # 手动触发压缩（未超阈值时）
    cm2 = ContextManager(session_id="test_compact2", max_tokens=100000,
                        auto_compact=False)
    cm2.add_step({
        "step_index": 0, "step_name": "s0", "capability": "x",
        "ok": True, "output": {"content": "hello"},
    })
    result = cm2.compact_if_needed()
    check("未超阈值时 compact_if_needed 返回 compacted=False",
          result["compacted"] is False, f"got {result}")


# ═══════════════════════════════════════════════════════════════
# 4. 跨会话持久化
# ═══════════════════════════════════════════════════════════════

def test_persistence():
    print("\n[4] 跨会话持久化")
    from kernel.context.context_manager import ContextManager

    cm = ContextManager(session_id="test_persist", max_tokens=5000)
    cm.add_step({
        "step_index": 0, "step_name": "search", "capability": "web.search",
        "ok": True, "output": {"content": "search result"},
    })
    cm.add_step({
        "step_index": 1, "step_name": "fetch", "capability": "web.fetch",
        "ok": False, "error": "timeout", "output": {},
    })

    # 持久化
    path = cm.persist()
    check("persist 返回非空路径", bool(path), f"path={path}")
    check("持久化文件存在", os.path.exists(path))

    # 加载
    loaded = ContextManager.load("test_persist")
    check("load 返回 ContextManager", loaded is not None)
    check("loaded session_id 一致", loaded.session_id == "test_persist")
    check("loaded entries 数量一致", len(loaded._entries) == 2)
    check("loaded max_tokens 一致", loaded.max_tokens == 5000)

    # 加载不存在的会话
    not_found = ContextManager.load("definitely_not_exists_xyz123")
    check("load 不存在的会话返回 None", not_found is None)


# ═══════════════════════════════════════════════════════════════
# 5. 全局会话注册表
# ═══════════════════════════════════════════════════════════════

def test_session_registry():
    print("\n[5] 全局会话注册表")
    from kernel.context.context_manager import (
        get_session, list_sessions, delete_session, reset_sessions_for_test,
    )

    reset_sessions_for_test()

    # 创建两个会话
    cm1 = get_session("sess_A", max_tokens=4000)
    cm2 = get_session("sess_B", max_tokens=6000)
    check("get_session 返回不同实例", cm1 is not cm2)
    check("get_session 复用同 ID", get_session("sess_A") is cm1)

    # 列出
    sessions = list_sessions()
    check("list_sessions 返回 2 个", len(sessions) == 2, f"got {len(sessions)}")
    check("list_sessions 包含 stats", "session_id" in sessions[0])

    # 删除
    ok = delete_session("sess_A")
    check("delete_session 返回 True", ok is True)
    check("删除后 list_sessions 返回 1 个", len(list_sessions()) == 1)

    reset_sessions_for_test()


# ═══════════════════════════════════════════════════════════════
# 6. OrchestrationChiplet 集成
# ═══════════════════════════════════════════════════════════════

def test_orchestrator_integration():
    print("\n[6] OrchestrationChiplet 集成")
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
    from kernel.context.context_manager import (
        reset_sessions_for_test, _sessions,
    )
    from core.fabric.adapter import InvokeRequest
    from core.fabric.capability import Capability

    reset_sessions_for_test()

    # 模拟路由函数：成功返回
    def fake_route(cap, payload):
        class FakeRes:
            ok = True
            data = {"content": f"handled {cap}"}
            engine_id = "fake_engine"
        return FakeRes()

    orch = OrchestrationChiplet(route_fn=fake_route)

    # 不传 context_session_id —— 不应创建会话
    req = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {"task": "test"},
        "steps": [{"capability": "bench.ping", "in": {}}],
    })
    res = orch.invoke(req)
    check("无 context_session_id 时正常完成", res.ok)
    check("无 context_session_id 时未创建会话",
          len(_sessions) == 0, f"_sessions={list(_sessions.keys())}")

    # 传 context_session_id —— 应创建会话并记录步骤
    req2 = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {"task": "test with ctx"},
        "steps": [
            {"capability": "bench.ping", "in": {}},
            {"capability": "bench.ping2", "in_from": "previous"},
        ],
        "context_session_id": "orch_sess_1",
        "context_max_tokens": 10000,
    })
    res2 = orch.invoke(req2)
    check("传 context_session_id 时正常完成", res2.ok)
    check("传 context_session_id 时创建了会话",
          "orch_sess_1" in _sessions, f"_sessions={list(_sessions.keys())}")

    cm = _sessions["orch_sess_1"]
    # 2 个步骤 + 1 个 summary = 3 条
    check("会话记录了 3 条 entries（2 步 + 1 summary）",
          len(cm._entries) == 3, f"got {len(cm._entries)}")
    check("会话 summary 在最后",
          cm._entries[-1].step_name == "orchestration_summary")

    # 持久化文件应已生成
    from kernel.context.context_manager import _session_path
    path = _session_path("orch_sess_1")
    check("持久化 JSONL 文件已生成", os.path.exists(path))

    reset_sessions_for_test()


# ═══════════════════════════════════════════════════════════════
# 7. WorkflowRunner 集成
# ═══════════════════════════════════════════════════════════════

def test_workflow_runner_integration():
    print("\n[7] WorkflowRunner 集成")
    from kernel.studio.workflow_runner import WorkflowRunner
    from kernel.studio.workflow_store import WorkflowStore
    from kernel.studio.workflow_models import Workflow, WorkflowStep
    from kernel.context.context_manager import (
        _sessions, reset_sessions_for_test, _session_path,
    )

    reset_sessions_for_test()

    # 用临时目录建 WorkflowStore
    import tempfile as _tf
    store_dir = _tf.mkdtemp(prefix="aos_wf_test_")
    store = WorkflowStore(base_dir=store_dir)

    # 创建一个简单工作流
    wf = Workflow.create(name="test_wf", description="test")
    wf.steps = [
        WorkflowStep(capability="bench.ping", name="step1", in_from="initial"),
        WorkflowStep(capability="bench.ping", name="step2", in_from="previous"),
    ]
    store.save(wf)

    # 模拟 route_fn
    def fake_route(cap, payload):
        class FakeRes:
            ok = True
            data = {"content": f"handled {cap}"}
            engine_id = "fake_engine"
        return FakeRes()

    runner = WorkflowRunner(route_fn=fake_route, store=store, pulse=None)

    # 不传 context_session_id —— 不应创建会话
    run1 = runner.run(wf.id, input_data={"task": "test"})
    check("无 context_session_id 时正常完成",
          run1.status in ("success", "partial"))
    check("无 context_session_id 时未创建会话",
          len(_sessions) == 0, f"_sessions={list(_sessions.keys())}")

    # 传 context_session_id —— 应创建会话并记录步骤
    run2 = runner.run(wf.id, input_data={"task": "test with ctx"},
                      context_session_id="wf_sess_1")
    check("传 context_session_id 时正常完成",
          run2.status in ("success", "partial"))
    check("传 context_session_id 时创建了会话",
          "wf_sess_1" in _sessions, f"_sessions={list(_sessions.keys())}")

    cm = _sessions["wf_sess_1"]
    # 2 个步骤 + 1 个 summary = 3 条
    check("会话记录了 3 条 entries（2 步 + 1 summary）",
          len(cm._entries) == 3, f"got {len(cm._entries)}")
    check("会话 summary 在最后",
          cm._entries[-1].step_name == "workflow_summary")

    # 持久化文件
    path = _session_path("wf_sess_1")
    check("持久化 JSONL 文件已生成", os.path.exists(path))

    reset_sessions_for_test()


# ═══════════════════════════════════════════════════════════════
# 8. API 端点
# ═══════════════════════════════════════════════════════════════

def test_api_endpoints():
    print("\n[8] API 端点")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.context_api import mount_context_api
    from kernel.context.context_manager import reset_sessions_for_test

    reset_sessions_for_test()

    app = FastAPI()
    mount_context_api(app)
    client = TestClient(app)

    # 列出会话（空）
    r = client.get("/api/context/sessions")
    check("GET /api/context/sessions 200", r.status_code == 200)
    check("初始会话数为 0", len(r.json()["sessions"]) == 0)

    # 创建会话
    r = client.post("/api/context/sessions", json={
        "session_id": "api_test", "max_tokens": 5000, "preserve_recent": 3,
    })
    check("POST /api/context/sessions 200", r.status_code == 200)
    check("创建会话返回 session_id", r.json()["session_id"] == "api_test")

    # 获取统计
    r = client.get("/api/context/sessions/api_test")
    check("GET /api/context/sessions/{id} 200", r.status_code == 200)
    check("stats total_entries=0", r.json()["stats"]["total_entries"] == 0)

    # 404 测试
    r = client.get("/api/context/sessions/not_exists")
    check("GET 不存在的会话 404", r.status_code == 404)

    # 添加消息
    r = client.post("/api/context/sessions/api_test/messages", json={
        "role": "user", "content": "hello world", "priority": "normal",
    })
    check("POST messages 200", r.status_code == 200)
    check("添加消息后 total_entries=1",
          r.json()["stats"]["total_entries"] == 1)

    # 添加步骤
    r = client.post("/api/context/sessions/api_test/steps", json={
        "step_index": 0, "step_name": "search",
        "capability": "web.search", "ok": True, "error": "",
        "output": {"content": "result"},
    })
    check("POST steps 200", r.status_code == 200)
    check("添加步骤后 total_entries=2",
          r.json()["stats"]["total_entries"] == 2)

    # 列出条目
    r = client.get("/api/context/sessions/api_test/entries")
    check("GET entries 200", r.status_code == 200)
    check("entries 返回 2 条", r.json()["count"] == 2)

    # 按优先级过滤
    r = client.get("/api/context/sessions/api_test/entries?priority=critical")
    check("GET entries?priority=critical 200", r.status_code == 200)

    # 获取上下文文本
    r = client.get("/api/context/sessions/api_test/text")
    check("GET text 200", r.status_code == 200)
    check("text 非空", len(r.json()["text"]) > 0)

    # 持久化
    r = client.post("/api/context/sessions/api_test/persist")
    check("POST persist 200", r.status_code == 200)
    check("persist 返回路径", bool(r.json()["path"]))

    # 加载
    # 先删内存中的会话
    from kernel.context.context_manager import _sessions, _sessions_lock
    with _sessions_lock:
        _sessions.pop("api_test", None)
    r = client.post("/api/context/sessions/api_test/load")
    check("POST load 200", r.status_code == 200)
    check("load 后 total_entries=2",
          r.json()["stats"]["total_entries"] == 2)

    # 压缩
    r = client.post("/api/context/sessions/api_test/compact")
    check("POST compact 200", r.status_code == 200)
    check("compact 返回 result 字段", "result" in r.json())

    # 清空
    r = client.post("/api/context/sessions/api_test/clear")
    check("POST clear 200", r.status_code == 200)
    check("clear 后 total_entries=0",
          r.json()["stats"]["total_entries"] == 0)

    # 删除
    r = client.delete("/api/context/sessions/api_test")
    check("DELETE 200", r.status_code == 200)

    # 验证已删除
    r = client.get("/api/context/sessions/api_test")
    check("DELETE 后 GET 返回 404", r.status_code == 404)

    reset_sessions_for_test()


# ═══════════════════════════════════════════════════════════════
# 9. 优雅降级
# ═══════════════════════════════════════════════════════════════

def test_graceful_degradation():
    print("\n[9] 优雅降级")
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
    from kernel.context.context_manager import _sessions, reset_sessions_for_test
    from core.fabric.adapter import InvokeRequest
    from core.fabric.capability import Capability

    reset_sessions_for_test()

    def fake_route(cap, payload):
        class FakeRes:
            ok = True
            data = {"content": "ok"}
            engine_id = "fake"
        return FakeRes()

    orch = OrchestrationChiplet(route_fn=fake_route)

    # context_enabled=False —— 不应创建会话
    req = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {"task": "test"},
        "steps": [{"capability": "bench.ping", "in": {}}],
        "context_session_id": "should_not_create",
        "context_enabled": False,
    })
    res = orch.invoke(req)
    check("context_enabled=False 时正常完成", res.ok)
    check("context_enabled=False 时未创建会话",
          "should_not_create" not in _sessions)

    # context_auto_persist=False —— 应创建会话但不持久化
    req2 = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {"task": "test"},
        "steps": [{"capability": "bench.ping", "in": {}}],
        "context_session_id": "no_persist",
        "context_auto_persist": False,
    })
    res2 = orch.invoke(req2)
    check("context_auto_persist=False 时正常完成", res2.ok)
    check("context_auto_persist=False 时创建了会话",
          "no_persist" in _sessions)

    # 验证未持久化
    from kernel.context.context_manager import _session_path
    path = _session_path("no_persist")
    check("context_auto_persist=False 时未生成 JSONL",
          not os.path.exists(path))

    reset_sessions_for_test()


# ═══════════════════════════════════════════════════════════════
# 10. 既有行为兼容
# ═══════════════════════════════════════════════════════════════

def test_backward_compat():
    print("\n[10] 既有行为兼容")
    from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
    from core.fabric.adapter import InvokeRequest
    from core.fabric.capability import Capability

    def fake_route(cap, payload):
        class FakeRes:
            ok = True
            data = {"content": "ok"}
            engine_id = "fake"
        return FakeRes()

    orch = OrchestrationChiplet(route_fn=fake_route)

    # 旧的 spec 格式（无任何 context_* 字段）
    req = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {"task": "old style"},
        "steps": [
            {"capability": "bench.ping", "in": {}},
            {"capability": "bench.ping2", "in_from": "previous"},
        ],
    })
    res = orch.invoke(req)
    check("旧 spec 正常完成", res.ok)
    check("旧 spec 返回 ok_steps=2",
          res.data.get("ok_steps") == 2, f"got {res.data}")
    check("旧 spec 返回 trace",
          isinstance(res.data.get("trace"), list))

    # 失败步骤也正常处理（不影响主流程）
    from core.fabric.adapter import InvokeResult
    def fail_route(cap, payload):
        return InvokeResult(ok=False, error="boom", engine_id="fail_eng")

    orch2 = OrchestrationChiplet(route_fn=fail_route)
    req2 = InvokeRequest(capability=Capability.WORKFLOW_EXECUTE, payload={
        "initial": {},
        "steps": [{"capability": "bench.fail", "in": {}}],
    })
    res2 = orch2.invoke(req2)
    check("失败步骤时正常返回（不抛异常）", res2.ok is False)
    check("失败步骤时 data 含 ok_steps=0",
          res2.data.get("ok_steps") == 0, f"got {res2.data}")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("Task 2: Context Engineering —— 端到端验证")
    print("=" * 70)

    test_context_manager_basics()
    test_priority_mechanism()
    test_compaction()
    test_persistence()
    test_session_registry()
    test_orchestrator_integration()
    test_workflow_runner_integration()
    test_api_endpoints()
    test_graceful_degradation()
    test_backward_compat()

    print("\n" + "=" * 70)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print("=" * 70)
    if FAIL > 0:
        print("\n失败项:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n全部通过 ✓")


if __name__ == "__main__":
    main()
