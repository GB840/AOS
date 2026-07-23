"""FreeLLMAPI 适配器测试（真实 HTTP 往返，非 mock）。

不 mock 网络：本测试起一个**真实**的 OpenAI 兼容本地服务
（ThreadingHTTPServer，实现 /v1/models 与 /v1/chat/completions 的真实协议），
让 AOS 的 FreeLLMAPIAdapter 真打过去、真解析回来，验证：
  ① health() 真实探测 /v1/models 成功
  ② invoke() 真实 POST /v1/chat/completions 并解析 choices[].message.content
  ③ 不可达时 ok=False（诚实降级，宪法 §6）
这证明适配器对接的是真实 OpenAI 协议，换上真实 FreeLLMAPI（自托管/托管）
只需改 AOS_FREELLMAPI_URL，无需改代码。

运行：主机 Python `python tests/test_freellmapi_adapter.py` 或 `pytest tests/ -q`。
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from core.fabric.adapter import InvokeRequest  # noqa: E402
from core.fabric.capability import Capability  # noqa: E402
from core.fabric.adapters.freellmapi_adapter import (  # noqa: E402
    FreeLLMAPIAdapter,
    is_freellmapi_configured,
)


class _OpenAIServer(BaseHTTPRequestHandler):
    """真实 OpenAI 兼容服务（测试桩，但协议真实）。"""

    def _send(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self._send({"object": "list",
                        "data": [{"id": "gpt-oss-120b", "object": "model"}]})
        elif self.path == "/health":
            self._send({"status": "ok"})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            req = json.loads(raw or b"{}")
        except Exception:
            req = {}
        if self.path == "/v1/chat/completions":
            msgs = req.get("messages", [])
            user_text = ""
            for m in msgs:
                if m.get("role") == "user":
                    user_text = m.get("content", "")
            # 真实回包：OpenAI 形状，把用户的话 echo 回来证明链路打通
            self._send({
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": req.get("model", "gpt-oss-120b"),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant",
                                "content": f"[freellmapi-echo] {user_text}"},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            })
        else:
            self._send({"error": "not found"}, 404)

    def log_message(self, *args):  # 静默
        pass


_PORT = 0
_SERVER = None


def _start_server():
    global _SERVER
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAIServer)
    srv.timeout = 5
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _SERVER = srv
    return srv.server_address[1]


def _stop_server():
    if _SERVER:
        _SERVER.shutdown()
        _SERVER.server_close()


def test_health_real_probe():
    """真实 GET /v1/models 探测成功。"""
    port = _start_server()
    try:
        a = FreeLLMAPIAdapter(url=f"http://127.0.0.1:{port}")
        assert a.health() is True
    finally:
        _stop_server()


def test_invoke_real_roundtrip():
    """真实 POST /v1/chat/completions 并解析 content（验证完整链路）。"""
    port = _start_server()
    try:
        a = FreeLLMAPIAdapter(url=f"http://127.0.0.1:{port}", model="gpt-oss-120b")
        res = a.invoke(InvokeRequest(
            capability=Capability.LLM_GATEWAY,
            payload={"messages": [{"role": "user", "content": "护眼测试"}]},
        ))
        assert res.ok is True, res.error
        assert "护眼测试" in res.data["content"], res.data
        assert res.data["model"] == "gpt-oss-120b"
    finally:
        _stop_server()


def test_invoke_unreachable_honest_failure():
    """不可达端口：如实 ok=False（绝不伪造成功，宪法 §6）。"""
    a = FreeLLMAPIAdapter(url="http://127.0.0.1:1")  # 端口 1 必不可达
    res = a.invoke(InvokeRequest(
        capability=Capability.LLM_GATEWAY,
        payload={"messages": [{"role": "user", "content": "hi"}]},
    ))
    assert res.ok is False
    assert res.error


def test_env_gate():
    """env 门控：未配 AOS_FREELLMAPI_URL 视为未启用。"""
    old = os.environ.pop("AOS_FREELLMAPI_URL", None)
    try:
        assert is_freellmapi_configured() is False
    finally:
        if old is not None:
            os.environ["AOS_FREELLMAPI_URL"] = old


if __name__ == "__main__":
    test_health_real_probe()
    test_invoke_real_roundtrip()
    test_invoke_unreachable_honest_failure()
    test_env_gate()
    print("ALL FREELLMAPI ADAPTER TESTS PASSED")
