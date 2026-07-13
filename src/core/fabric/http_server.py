"""FabricHub HTTP serving mode — the "single kernel, one port" front door.

Phase 1a of the v5 -> FabricHub consolidation. PURELY ADDITIVE: this module
does NOT touch brain.py / deerflow / the v5 FastAPI app. It exposes FabricHub
as a lightweight HTTP service (stdlib only, zero new deps) so FabricHub can act
as the *single runtime* the architecture demands, while v5 keeps running on
:8000 until Phase 2 flips the entry point (rollback via AOS_RUNTIME=v5|fabrichub).

Endpoints:
  GET  /                       service info
  GET  /health                 liveness  (must be instant, never blocks)
  GET  /health/deep           readiness (hub.health_report)
  GET  /api/engines           alias of /health/deep
  POST /api/chat              {"message","session_id"} -> inference.llm route
  POST /api/run_task          {"task","planner","session_id"} -> hub.run_task
  POST /api/mcp               JSON-RPC -> reused MCPProtocol (aos_* tools)
  GET  /api/mcp/info          MCP server info
  POST /api/3d/generate       {"prompt"} -> interactive 3D scene url (MEDIA_3D)
  GET  /scene/{id}            serve the generated 3D scene HTML (browser-interactive)

The HTTP MCP path reuses src.mcp.protocol.MCPProtocol verbatim, so FabricHub
instantly gains an HTTP MCP surface that mirrors v5's /api/mcp shape — the two
runtimes become interoperable WITHOUT duplicating any tool logic. Both routes
share the very same FabricHub singleton (via mcp.protocol._get_hub), honouring
the architecture-first principle: one kernel owns routing/memory/context.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

# Local imports (repo root is on sys.path when launched via scripts/aos.py).
from kernel.wiring import build_fabric_hub
# Reuse the exact same MCPProtocol + its FabricHub singleton (_get_hub) so the
# HTTP MCP surface and the /api/chat route share ONE kernel. The underscore
# import is intentional: we deliberately bind to the protocol layer's already
# validated singleton rather than spinning up a second FabricHub.
from mcp.protocol import MCPProtocol, _get_hub
from core.fabric.adapter import InvokeRequest

__all__ = ["serve", "FabricHubHTTPHandler"]


def _load_dotenv_best_effort() -> None:
    """best-effort load repo-root .env (real API keys) without clobbering env."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        # src/core/fabric/http_server.py -> repo root is three levels up.
        root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
        env_path = os.path.join(root, ".env")
        if not os.path.exists(env_path):
            return
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except Exception:
        pass


# One protocol instance reused for every /api/mcp request. Its handlers call
# the shared _get_hub() — never builds a second kernel.
_MCP = MCPProtocol()

# In-memory store of generated interactive 3D scenes (scene_id -> record).
# Prototype: scenes live for the server's lifetime; persist to disk if needed later.
_SCENES: dict[str, dict] = {}


def _generate_3d(prompt: str) -> dict:
    """Generate an interactive 3D scene from a prompt.

    Strategy (honours the 端云合作 / 本地兜底 principle):
      1. Direct adapter first — ThreejsAdapter is zero-dependency, deterministic,
         instant. The endpoint never blocks on a heavy kernel build.
      2. FabricHub route as fallback — if a future remote 3D provider is
         registered, the unified router still works.
    Returns {"ok": True, "html": ..., "mode": ...} or {"ok": False, "error": ...}.
    """
    # 1) direct adapter (local, instant, always available)
    try:
        from core.fabric.adapters.threejs_adapter import ThreejsAdapter
        r = ThreejsAdapter().invoke(
            InvokeRequest(capability="media.3d", payload={"prompt": prompt})
        )
        if r.ok and r.data and r.data.get("html"):
            return {"ok": True, "html": r.data["html"], "mode": r.data.get("mode")}
    except Exception as e:  # noqa: BLE001
        logger.warning("3D 直连适配器失败，尝试 hub 路由: %s", e)
    # 2) fallback: unified FabricHub routing
    try:
        hub = _get_hub()
        r = hub.route("media.3d", {"prompt": prompt})
        if r.ok and r.data and r.data.get("html"):
            return {"ok": True, "html": r.data["html"], "mode": r.data.get("mode")}
    except Exception as e:  # noqa: BLE001
        logger.warning("3D hub 路由失败: %s", e)
    return {"ok": False, "error": "3D 生成失败（适配器与 hub 均未返回有效结果）"}


def _extract_text(data: object) -> str:
    """Best-effort pull a human-readable answer out of an adapter result."""
    if isinstance(data, dict):
        for key in ("content", "text", "message", "reply", "output"):
            v = data.get(key)
            if isinstance(v, str) and v.strip():
                return v
        for v in data.values():  # one level of nesting
            if isinstance(v, dict):
                nested = _extract_text(v)
                if nested:
                    return nested
    if isinstance(data, str):
        return data
    return ""


class FabricHubHTTPHandler(BaseHTTPRequestHandler):
    """Minimal JSON HTTP front door onto FabricHub. Each request touches the
    shared kernel lazily (first request builds it); failures are caught and
    returned as JSON so the server process never dies on a bad call."""

    server_version = "AOS-FabricHub/1.0"

    # ---- boilerplate ----
    def log_message(self, fmt, *args):  # quieter than default stderr spam
        logger.debug("http %s - %s", self.address_string(), fmt % args)

    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8")) or {}
        except Exception:
            return {}

    # ---- routing ----
    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            return self._send_json(self._info())
        if path == "/health":
            return self._send_json(
                {"status": "alive", "service": "aos-fabrichub", "ts": time.time()}
            )
        if path in ("/health/deep", "/api/engines"):
            try:
                return self._send_json(_get_hub().health_report())
            except Exception as e:
                return self._send_json({"ok": False, "error": str(e)})
        if path == "/api/mcp/info":
            return self._send_json(_MCP.get_server_info())
        if path.startswith("/scene/"):
            return self._serve_scene(path[len("/scene/"):])
        return self._send_json({"error": "not found", "path": path}, status=404)

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        body = self._read_json_body()
        if path == "/api/chat":
            return self._post_chat(body)
        if path == "/api/run_task":
            return self._post_run_task(body)
        if path == "/api/mcp":
            return self._post_mcp(body)
        if path == "/api/3d/generate":
            return self._post_3d_generate(body)
        return self._send_json({"error": "not found", "path": path}, status=404)

    # ---- endpoints ----
    def _info(self) -> dict:
        return {
            "service": "aos-fabrichub",
            "mode": "http-serving (Phase 1a consolidation)",
            "runtime_principle": "single FabricHub kernel, one port",
            "endpoints": {
                "health": "/health",
                "health_deep": "/health/deep",
                "engines": "/api/engines",
                "chat": "POST /api/chat  {\"message\": ...}",
                "run_task": "POST /api/run_task  {\"task\": ...}",
                "mcp": "POST /api/mcp  (JSON-RPC 2.0)",
                "mcp_info": "/api/mcp/info",
                "3d_generate": "POST /api/3d/generate  {\"prompt\": ...} -> 交互式 3D 场景 url",
                "3d_scene": "GET /scene/{scene_id}  (浏览器打开即可拖拽交互)",
            },
        }

    def _post_chat(self, body: dict) -> None:
        message = (body.get("message") or body.get("prompt") or "").strip()
        if not message:
            return self._send_json({"ok": False, "error": "message required"}, status=400)
        try:
            hub = _get_hub()
            res = hub.route(
                "inference.llm",
                {"prompt": message, "session_id": body.get("session_id")},
            )
            return self._send_json({
                "ok": bool(res.ok),
                "response": _extract_text(res.data) if res.data else "",
                "data": res.data,
                "error": res.error,
            })
        except Exception as e:  # noqa: BLE001 - never crash the server
            logger.exception("chat failed")
            return self._send_json({"ok": False, "error": str(e)})

    def _post_run_task(self, body: dict) -> None:
        task = (body.get("task") or "").strip()
        if not task:
            return self._send_json({"ok": False, "error": "task required"}, status=400)
        try:
            hub = _get_hub()
            result = hub.run_task(
                task,
                planner=body.get("planner", "ag2"),
                session_id=body.get("session_id"),
            )
            return self._send_json(result)
        except Exception as e:  # noqa: BLE001
            logger.exception("run_task failed")
            return self._send_json({"ok": False, "error": str(e)})

    def _post_mcp(self, body: dict) -> None:
        try:
            from mcp.protocol import MCPMessage
            msg = MCPMessage.from_json(json.dumps(body, ensure_ascii=False))
            reply = _MCP.handle_message(msg)
            return self._send_json(reply.to_dict())
        except Exception as e:  # noqa: BLE001
            logger.exception("mcp failed")
            return self._send_json({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "error": {"code": -32603, "message": str(e)},
            })


    def _post_3d_generate(self, body: dict) -> None:
        prompt = (body.get("prompt") or body.get("message") or "").strip()
        if not prompt:
            return self._send_json({"ok": False, "error": "prompt required"}, status=400)
        out = _generate_3d(prompt)
        if not out.get("ok"):
            return self._send_json({"ok": False, "error": out.get("error")}, status=500)
        sid = uuid.uuid4().hex[:12]
        _SCENES[sid] = {"html": out["html"], "prompt": prompt, "mode": out.get("mode")}
        return self._send_json({
            "ok": True,
            "scene_id": sid,
            "url": f"/scene/{sid}",
            "mode": out.get("mode"),
            "prompt": prompt,
            "note": "在浏览器打开 url 即可交互（拖拽旋转 / 滚轮缩放 / 自动旋转）。",
        })

    def _serve_scene(self, sid: str) -> None:
        rec = _SCENES.get(sid)
        if not rec:
            return self._send_json({"error": "scene not found"}, status=404)
        html = rec["html"].encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def serve(host: str = "0.0.0.0", port: int = 8123) -> None:
    """Start the FabricHub HTTP serving mode (blocking).

    The kernel is built lazily on the first request that needs it; this call
    returns as soon as the socket is bound, so /health stays instant even while
    the (heavy) isolation wiring spins up in the background.
    """
    _load_dotenv_best_effort()
    httpd = ThreadingHTTPServer((host, port), FabricHubHTTPHandler)
    logger.info(
        "AOS FabricHub HTTP serving on http://%s:%d (kernel built lazily on first use)",
        host, port,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("shutting down FabricHub HTTP server")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    # Allow `python src/core/fabric/http_server.py` directly.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    serve()
