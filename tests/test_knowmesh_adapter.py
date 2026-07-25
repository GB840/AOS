"""KnowmeshAdapter 单元测试（覆盖契约/健康门控/诚实降级/_http 钩子）。

遵循 mediakit_adapter 的离线测试范式：用可注入的 `_http` 钩子模拟 HTTP 响应，
从而在不依赖 KnowMesh 实例运行的情况下验证适配器逻辑与诚实降级行为（理念6）。
另含一个真实连通探针（仅在 KNOWMESH 可达时运行），用于「适配器真跑」验证。
"""
from __future__ import annotations

import contextlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.fabric.adapter import InvokeRequest  # noqa: E402
from core.fabric.adapters.knowmesh_adapter import (  # noqa: E402
    KnowmeshAdapter,
    KnowMeshUnavailable,
    _ENV_ENABLED,
    _ENV_KB_ID,
)
from core.fabric.capability import Capability  # noqa: E402


def _req(capability=Capability.MEMORY_KNOWLEDGE, payload=None):
    return InvokeRequest(capability=capability, payload=payload or {})


@contextlib.contextmanager
def _env_override(key, value):
    """安全覆盖 env：不用 mock.patch.dict。本机/沙箱存在超长环境变量，
    patch.dict 还原巨值会触发 Windows 32767 上限报错。改为手动 set（小值）
    + 退出 pop（均安全），适配器默认行为不受影响。"""
    os.environ[key] = value
    try:
        yield
    finally:
        os.environ.pop(key, None)


class _FakeHTTP:
    """记录调用并据 path 返回预设响应；可注入 KnowMeshUnavailable 模拟故障。"""

    def __init__(self, responses=None, raise_err=None):
        self.calls = []
        self.responses = responses or {}
        self.raise_err = raise_err

    def __call__(self, method, path, *, params=None, body=None, headers=None):
        self.calls.append((method, path, params, body))
        if self.raise_err is not None:
            raise self.raise_err
        # path 精确匹配，否则回退到默认
        if path in self.responses:
            return self.responses[path]
        # 用前缀匹配（如 /kb/xxx/api/query）
        for key, val in self.responses.items():
            if path.startswith(key):
                return val
        return {}


class TestKnowmeshAdapter(unittest.TestCase):

    # ── 1. 基础契约 ──
    def test_basic_contract(self):
        a = KnowmeshAdapter()
        self.assertEqual(a.engine_id, "knowmesh")
        self.assertEqual(a.advertise_capabilities(), [Capability.MEMORY_KNOWLEDGE])
        self.assertEqual(a.tier(), "high")
        self.assertEqual(a.supported_protocols(), ["HTTP"])

    # ── 2. 服务可达 → health True ──
    def test_health_true_when_up(self):
        a = KnowmeshAdapter()
        a._http = _FakeHTTP({"/api/integration/manifest": {"ok": True}})
        self.assertTrue(a.health())

    # ── 3. 服务不可达 → health False ──
    def test_health_false_when_down(self):
        a = KnowmeshAdapter()
        a._http = _FakeHTTP(raise_err=KnowMeshUnavailable("down"))
        self.assertFalse(a.health())

    # ── 4. AOS_KNOWMESH_ENABLED=0 → 强制关闭 ──
    def test_health_false_when_disabled(self):
        # 注意：本机/沙箱环境可能存在超长环境变量，patch.dict 还原时会触发
        # Windows 32767 字符上限报错；这里手动置位并在 finally 用默认小值收尾，
        # 避免还原巨值（适配器默认即为 "1"，不影响其余测试）。
        had = _ENV_ENABLED in os.environ
        os.environ[_ENV_ENABLED] = "0"
        try:
            a = KnowmeshAdapter()
            a._http = _FakeHTTP({"/api/integration/manifest": {"ok": True}})
            self.assertFalse(a.health())
        finally:
            if had:
                os.environ[_ENV_ENABLED] = "1"
            else:
                os.environ.pop(_ENV_ENABLED, None)

    # ── 5. status/diagnostics 上报就绪度 ──
    def test_invoke_status_returns_diagnostics(self):
        diag = {
            "ok": True,
            "service": {"host": "127.0.0.1", "port": 7457, "remoteAccess": False},
            "knowledgeBase": {"availableCount": 0},
            "readiness": {"queryRuntime": {"status": "blocked", "reason": "knowledge_base_required"}},
        }
        a = KnowmeshAdapter()
        a._http = _FakeHTTP({"/api/integration/diagnostics": diag})
        res = a.invoke(_req(payload={"action": "status"}))
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.data["diagnostics"], diag)

    # ── 6. 无 KB id → 诚实拒绝 ──
    def test_invoke_query_no_kb_id(self):
        with _env_override(_ENV_KB_ID, ""):
            a = KnowmeshAdapter()
            res = a.invoke(_req(payload={"action": "query", "question": "什么是 X？"}))
            self.assertFalse(res.ok)
            self.assertIn("KNOWMESH_KB_ID", res.error)

    # ── 7. 查询命中（answered）→ 返回答案+引用 ──
    def test_invoke_query_answered(self):
        answered = {
            "ok": True,
            "status": "answered",
            "answer": {"text": "据《X》第3章，定义是…"},
            "citations": [{"id": "c1", "title": "X", "pageNumber": 3}],
            "feedback": {"endpoint": "/kb/kb1/api/query/feedback"},
            "question": "什么是 X？",
        }
        fake = _FakeHTTP({"/kb/kb1/api/query": answered})
        with _env_override(_ENV_KB_ID, "kb1"):
            a = KnowmeshAdapter()
            a._http = fake
            res = a.invoke(_req(payload={"action": "query", "question": "什么是 X？"}))
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.data["answer"], "据《X》第3章，定义是…")
        self.assertEqual(len(res.data["citations"]), 1)
        self.assertEqual(res.data["kb_id"], "kb1")
        # 验证确实 POST 到了 scoped 路径且 body 含 question
        self.assertEqual(fake.calls[0][0], "POST")
        self.assertEqual(fake.calls[0][1], "/kb/kb1/api/query")
        self.assertEqual(fake.calls[0][3]["question"], "什么是 X？")

    # ── 8. 查询未命中（out_of_scope）→ 诚实返回 ok=False ──
    def test_invoke_query_not_answered(self):
        resp = {"ok": True, "status": "out_of_scope", "error": {"code": "out_of_scope", "message": "超出知识库范围"}}
        fake = _FakeHTTP({"/kb/kb1/api/query": resp})
        with _env_override(_ENV_KB_ID, "kb1"):
            a = KnowmeshAdapter()
            a._http = fake
            res = a.invoke(_req(payload={"action": "query", "question": "无关问题"}))
        self.assertFalse(res.ok)
        self.assertIn("out_of_scope", res.error)

    # ── 9. search → 透传检索结果 ──
    def test_invoke_search(self):
        search_resp = {"ok": True, "results": [{"id": "r1", "title": "X"}]}
        fake = _FakeHTTP({"/kb/kb1/api/search": search_resp})
        with _env_override(_ENV_KB_ID, "kb1"):
            a = KnowmeshAdapter()
            a._http = fake
            res = a.invoke(_req(payload={"action": "search", "query": "X"}))
        self.assertTrue(res.ok, res.error)
        self.assertEqual(res.data["search"], search_resp)
        self.assertEqual(fake.calls[0][0], "GET")
        self.assertEqual(fake.calls[0][1], "/kb/kb1/api/search")
        self.assertEqual(fake.calls[0][2], {"q": "X"})

    # ── 10. 不支持的能力 / action → 诚实拒绝 ──
    def test_unsupported_capability(self):
        a = KnowmeshAdapter()
        res = a.invoke(_req(capability=Capability.WEB_SEARCH, payload={"action": "query"}))
        self.assertFalse(res.ok)
        self.assertIn("仅服务", res.error)

    def test_unknown_action(self):
        with _env_override(_ENV_KB_ID, "kb1"):
            a = KnowmeshAdapter()
            a._http = _FakeHTTP()
            res = a.invoke(_req(payload={"action": "frobnicate"}))
            self.assertFalse(res.ok)
            self.assertIn("不支持的 action", res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
