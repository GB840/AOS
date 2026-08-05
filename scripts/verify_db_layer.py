"""临时验证脚本：绕开 conftest/brain 完整依赖，独立验证数据库层全链路。"""
import os
import sys
import tempfile
import sqlite3
import subprocess

sys.path.insert(0, "src")

from sqlmodel import SQLModel, select
from sqlalchemy.exc import IntegrityError
from core.database import init_db, models, session_scope
from core.database.models import (
    Agent, AuditLog, EvolutionLog, Message, Thread,
    Notification,
)

tmp = tempfile.mkdtemp()
from utils.config import config
config.SQLITE_DB_PATH = os.path.join(tmp, "aos.db")

fails = []


def check(name, cond):
    print(("  PASS " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


init_db()
check("42 表注册", models.TABLE_COUNT == 42)
check("metadata 表数=42", len(SQLModel.metadata.tables) == 42)

init_db()
init_db()
check("init_db 幂等", True)

with session_scope() as s:
    ids = {a.agent_id for a in s.exec(select(Agent)).all()}
check("seed agents", {"hermes", "deerflow", "meta_orchestrator"} <= ids)

boot_aid = None
with session_scope() as s:
    s.add(AuditLog(event_type="boot", agent_id="hermes"))
    s.commit()
    row = s.exec(select(AuditLog).where(AuditLog.event_type == "boot")).first()
    boot_aid = row.agent_id if row is not None else None
check("ORM 读写", boot_aid == "hermes")

# FK 约束生效 + 级联删除 (确保外键真的在起作用，而非纸面定义)
fk_ok = False
cascade_ok = False
try:
    with session_scope() as s:
        s.add(Thread(thread_id="t_fk", title="fk-test"))
        s.commit()
        # 引用不存在的 thread -> 必须触发 IntegrityError (否则 FK 没生效 = 漏洞)
        try:
            s.add(Message(thread_id="__nope__", role="user", content="x"))
            s.commit()
            fk_ok = False
        except IntegrityError:
            s.rollback()
            fk_ok = True
        # 级联删除: 删 thread -> 同 thread_id 的 messages 应被级联删
        s.add(Message(thread_id="t_fk", role="user", content="child"))
        s.commit()
        s.exec(Thread.__table__.delete().where(Thread.thread_id == "t_fk"))
        s.commit()
        remain = s.exec(select(Message).where(Message.thread_id == "t_fk")).all()
        cascade_ok = len(remain) == 0
    check("FK 约束生效(拒绝孤儿消息)", fk_ok)
    check("级联删除生效(ondelete=CASCADE)", cascade_ok)
except Exception as e:  # 整段异常也不应静默通过
    check("FK 约束生效(拒绝孤儿消息)", False)
    check("级联删除生效(ondelete=CASCADE)", False)
    print("   FK/cascade 测试异常:", repr(e))

con = sqlite3.connect(config.SQLITE_DB_PATH)
con.execute("INSERT INTO threads (thread_id,title) VALUES ('t_raw','x')")
con.execute("INSERT INTO audit_log (event_type,agent_id) VALUES ('x','hermes')")
con.commit()
check("裸SQL 省时间戳不报错", con.execute("SELECT count(*) FROM threads WHERE thread_id='t_raw'").fetchone()[0] == 1)
con.close()

init_db()
from deerflow.persistence_bridge import AOSPersistenceBridge
pb = AOSPersistenceBridge()
pb.create_thread("t_pb", "x")
pb.add_message("t_pb", "user", "hi")
st = pb.get_stats()
pb.close()
check("persistence_bridge 读写", st["threads"] >= 1 and st["messages"] >= 1)

from memory import MemoryManager
mem = MemoryManager()
mem.add_conversation("s", "u", "hi mem")
mem.add_knowledge("d", "body", "s", ["t"])
mem.close()
con = sqlite3.connect(config.SQLITE_DB_PATH)
check("memory FTS 虚拟表", len(con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations_fts'").fetchall()) == 1)
con.close()

from meta_orchestrator.engine import MetaOrchestratorEngine, classify_intent
check("classify L3.5", classify_intent("让系统自我进化并修改策略")[0] == "L3.5")
e = MetaOrchestratorEngine()
r = e.route_intent("让系统自我进化并修改策略", user_id="hermes", project_id="p")
check("route 返回 workflow", r["workflow_id"] == "meta_orchestration")
# 成本-精度策略与优先级路径 (best-effort，不依赖 DB)
check("query_priority 返回整数", isinstance(e.query_priority(""), int))
# 误报回归: 含 "metadata" 的普通意图不应被判为 L3.5 (旧规则裸 meta 会误判)
check("classify 不含 meta 误判", classify_intent("update the metadata schema of the table")[0] == "L1")
evo_count = 0
evo_layer = None
with session_scope() as s:
    rows = s.exec(select(EvolutionLog)).all()
    evo_count = len(rows)
    evo_layer = rows[0].layer if rows else None
check("evolution_log 落库(L3.5)", evo_count >= 1 and evo_layer == "L3.5")

# ---- P0: 元调度接入主链路验证 (route_intent 返回 layer + 自修改提案落库) ----
check("route_intent 返回 layer", r.get("layer") == "L3.5")
prop = e.propose_self_modification("让系统自我进化并修改策略")
check("self_modification_proposal 生成(L3.5)", prop.get("status") == "pending_approval")

# ---- 新表 (Notification / EventStore / Snapshot / ColdMemory) ----
with session_scope() as s:
    s.add(Notification(agent_id="hermes", channel="in_app", payload_json='{"m":1}', read=False))
    s.commit()
check("Notification 新表可写", True)

# ---- 平台外壳 smoke (零重依赖, 依赖可探测/优雅降级) ----
from core.platform import (
    Metrics, Tracer, HealthAggregator, prometheus_exposition,
    CircuitBreaker, retry, fallback, degrade,
    IdempotencyStore, idempotent, RateLimiter,
    NotificationService, EventStore as ES,
    extract_text, PythonSandbox, WasmSandbox, ColdStore, Pipeline, CompatMatrix,
)

_m = Metrics()
_m.inc("req_total", 3, {"svc": "x"})
check("observability Metrics", _m.snapshot()["counters"].get("req_total{svc=x}") == 3.0)
_t = Tracer()
with _t.span("op"):
    pass
check("observability Tracer span", len(_t.spans()) == 1)
check("observability prometheus 导出", "aos_req_total" in prometheus_exposition(_m))
_h = HealthAggregator()
_h.register("db", lambda: {"status": "ok"})
check("observability Health", _h.check_all()["status"] == "healthy")

@retry(times=2)
def _flaky():
    raise ValueError("x")
_flaky_failed = 0
try:
    _flaky()
except ValueError:
    _flaky_failed = 1
check("resilience retry 最终抛出", _flaky_failed == 1)

@fallback(default="D")
def _boom():
    raise RuntimeError()
check("resilience fallback", _boom() == "D")

_cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
def _raiser():
    raise ValueError("x")
for _ in range(3):
    try:
        _cb.call(_raiser)
    except Exception:
        pass
check("resilience 熔断 open", _cb.state in ("open", "half-open"))
check("resilience degrade", degrade(lambda: 1 / 0)() is None)

_store = IdempotencyStore()
@idempotent(_store, lambda *a, **k: "k")
def _job():
    return "done"
check("middleware 幂等 首次", _job() == "done")
check("middleware 幂等 重复", _job().get("duplicated") is True)
_rl = RateLimiter(rate=100, capacity=2)
check("middleware 限流 放行", _rl.allow("u", 1) and _rl.allow("u", 1))
check("middleware 限流 拒绝", _rl.allow("u", 1) is False)

_ns = NotificationService()
_ns_res = _ns.send("hermes", {"msg": "hi"}, channels=["in_app"])
check("notify in_app 通道", _ns_res.get("in_app", {}).get("ok") is True)

_es = ES()
_s1 = _es.append("agent", "a1", "created", {"v": 1})
_s2 = _es.append("agent", "a1", "updated", {"v": 2})
_evs = _es.replay("agent", "a1")
check("eventstore 追加+回放", _s1 == 1 and _s2 == 2 and len(_evs) == 2)
_es.save_snapshot("agent", "a1", 2, {"state": "ok"})
_snap = _es.load_latest_snapshot("agent", "a1")
check("eventstore 快照", _snap is not None and _snap["version"] == 2)

_ft = extract_text(b"hello world", mime="text/plain")
check("fileproc 文本抽取", _ft["ok"] and _ft["text"] == "hello world")
_pdfr = extract_text(b"%PDF-1.4 fake", mime="application/pdf")
check("fileproc PDF 优雅降级", _pdfr["ok"] is False and "PDF" in _pdfr["error"])

_ps = PythonSandbox()
_pr = _ps.run("print('hi')")
check("sandbox Python 执行", _pr["ok"] and "hi" in _pr["stdout"])
_ws = WasmSandbox()
_wr = _ws.run("x")
check("sandbox WASM 接口(未装报错)", _wr["ok"] is False and "wasmtime" in _wr["error"])

_cs = ColdStore()
_cs.archive("c1", "conversation", {"text": "old"})
_restored = _cs.restore("c1")
check("cold 归档+还原", _restored == {"text": "old"})

_pl = Pipeline("ci").add("ok", lambda: True).add("fail_cont", lambda: False, on_fail="continue")
_prun = _pl.run()
check("devops 流水线 continue", _prun["aborted"] is False and len(_prun["steps"]) == 2)

_cm = CompatMatrix()
_cm.register("skill:x", "1.2.0", "ok")
check("compat 矩阵 兼容", _cm.is_compatible("skill:x", ">=1.0.0"))

dup = "class Foo:\n    def bar(self):\n        return 1\n    def bar(self):\n        return 2\n"
with open(os.path.join(tmp, "dup.py"), "w") as f:
    f.write(dup)
rc = subprocess.run([sys.executable, "scripts/check_ast_duplicates.py", os.path.join(tmp, "dup.py")], capture_output=True, text=True)
# ---- 并发安全回归 (memory.py / persistence_bridge.py 加锁后) ----
import threading as _th
_pb2 = AOSPersistenceBridge()
_pb_errs = []
def _w_pb(i):
    try:
        _pb2.create_thread(f"ct_{i}", "x")
        _pb2.add_message(f"ct_{i}", "user", f"m{i}")
        _pb2.get_stats()
    except Exception as ex:
        _pb_errs.append(repr(ex))
_ts = [_th.Thread(target=_w_pb, args=(i,)) for i in range(20)]
[t.start() for t in _ts]; [t.join() for t in _ts]
_pb2.close()
check("并发 persistence_bridge 无异常", len(_pb_errs) == 0)

config.VECTOR_ENABLED = False  # 隔离 sqlite 锁回归，避免向量库线程特性干扰
_mem2 = MemoryManager()
_mem_errs = []
def _w_mem(i):
    try:
        _mem2.add_conversation(f"s{i}", "u", f"c{i}")
        _mem2.add_knowledge(f"k{i}", "b", "s", ["t"])
        _mem2.get_conversation_history(f"s{i}")
    except Exception as ex:
        _mem_errs.append(repr(ex))
_ts2 = [_th.Thread(target=_w_mem, args=(i,)) for i in range(20)]
[t.start() for t in _ts2]; [t.join() for t in _ts2]
_mem2.close()
check("并发 memory 无异常", len(_mem_errs) == 0)

check("AST 检测重复(rc=1)", rc.returncode == 1)
clean = "class Foo:\n    def bar(self):\n        return 1\n    def baz(self):\n        return 2\n"
with open(os.path.join(tmp, "clean.py"), "w") as f:
    f.write(clean)
rc2 = subprocess.run([sys.executable, "scripts/check_ast_duplicates.py", os.path.join(tmp, "clean.py")], capture_output=True, text=True)
check("AST 干净(rc=0)", rc2.returncode == 0)

print("\n结果:", "ALL PASS ✅" if not fails else f"{len(fails)} FAIL: {fails}")
sys.exit(1 if fails else 0)
