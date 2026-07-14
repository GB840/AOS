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
  GET  /                       Living Companion Entry (3D 生命体伙伴首页, text/html)
  GET  /?info=1               service info (JSON, for API clients)
  GET  /api/companion         companion identity + state (双域记忆视图)
  POST /api/companion/message {"text"} -> 伙伴编排：感知/记忆/规划/执行/回应
  # 语音芯粒（方案三：语音是内核的一个可替换能力，非独立助手）
  POST /api/voice/stt         {"transcript"|"audio_path"|"audio_b64"} -> {text, engine}
  POST /api/voice/tts         {"text","voice?","lang?"} -> {text, audio_url, engine}
  POST /api/voice/turn        {"transcript"|"audio"*} -> 听→想→说 全链路 {reply, audio_url, mood, state}
  GET  /api/voice/info        STT/TTS 引擎可用性探测（诚实）
  GET  /api/voice/audio/{id}  托管 TTS 合成音频（mp3/wav）
  # LNN 轻量动态推理芯粒（液态神经网络时间序列预测；与 LLM 正交，高低搭配）
  POST /api/lnn/predict       {"series":[floats]|"demo":true,"horizon"?,"epochs"?} -> {forecast, engine, final_loss}
  GET  /api/lnn/info          LNN/LFM2 引擎可用性探测（诚实：numpy 永远 live，LFM2 需权重）

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
        try:
            body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionError, OSError):
            # 客户端已断开（负载下偶发）——吞掉，绝不回退成字符串错误页。
            pass

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
        raw = self.path
        path = raw.split("?", 1)[0].rstrip("/")
        if path in ("", "/"):
            # Living Companion Entry：浏览器打开就是 3D 生命体伙伴首页；
            # ?info=1 给 API 客户端返回 JSON 元信息。
            if "info=1" in raw:
                return self._send_json(self._info())
            return self._serve_living_home()
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
        if path == "/api/companion":
            return self._get_companion()
        # 人设配置化：GET /api/companion/{user_id}/persona
        if path.startswith("/api/companion/") and path.endswith("/persona"):
            uid = path[len("/api/companion/"):-len("/persona")].strip("/") or "default"
            return self._get_persona(uid)
        if path.startswith("/scene/"):
            return self._serve_scene(path[len("/scene/"):])
        if path == "/api/voice/info":
            return self._get_voice_info()
        if path.startswith("/api/voice/audio/"):
            return self._serve_voice_audio(path[len("/api/voice/audio/"):])
        if path == "/api/voice/wake/status":
            return self._get_voice_wake_status()
        if path == "/api/lnn/info":
            return self._get_lnn_info()
        if path == "/api/lnn/predict":  # POST below; GET 也允许(演示)
            return self._post_lnn_predict({})
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
        if path == "/api/companion/message":
            return self._post_companion_message(body)
        # 人设配置化：POST/PUT /api/companion/{user_id}/persona
        if path.startswith("/api/companion/") and path.endswith("/persona"):
            uid = path[len("/api/companion/"):-len("/persona")].strip("/") or "default"
            return self._put_persona(uid, body)
        if path == "/api/voice/stt":
            return self._post_voice_stt(body)
        if path == "/api/voice/tts":
            return self._post_voice_tts(body)
        if path == "/api/voice/turn":
            return self._post_voice_turn(body)
        if path == "/api/voice/wake/start":
            return self._post_voice_wake_start()
        if path == "/api/voice/wake/stop":
            return self._post_voice_wake_stop()
        if path == "/api/lnn/predict":
            return self._post_lnn_predict(body)
        return self._send_json({"error": "not found", "path": path}, status=404)

    def do_PUT(self):
        # 人设配置化也接受 PUT（语义更准）；路由与 POST 一致
        path = self.path.split("?", 1)[0].rstrip("/")
        body = self._read_json_body()
        if path.startswith("/api/companion/") and path.endswith("/persona"):
            uid = path[len("/api/companion/"):-len("/persona")].strip("/") or "default"
            return self._put_persona(uid, body)
        return self._send_json({"error": "not found", "path": path}, status=404)

    # ---- endpoints ----
    def _info(self) -> dict:
        return {
            "service": "aos-fabrichub",
            "mode": "http-serving (Phase 1a consolidation + Living Companion Entry)",
            "runtime_principle": "single FabricHub kernel, one port",
            "endpoints": {
                "health": "/health",
                "health_deep": "/health/deep",
                "engines": "/api/engines",
                "chat": "POST /api/chat  {\"message\": ...}",
                "run_task": "POST /api/run_task  {\"task\": ...}",
                "mcp": "POST /api/mcp  (JSON-RPC 2.0)",
                "mcp_info": "/api/mcp/info",
                "companion": "GET /api/companion  (生命体身份+状态)",
                "companion_message": "POST /api/companion/message  {\"text\": ...} -> 伙伴编排回应",
                "3d_generate": "POST /api/3d/generate  {\"prompt\": ...} -> 交互式 3D 场景 url",
                "3d_scene": "GET /scene/{scene_id}  (浏览器打开即可拖拽交互)",
                "living_home": "GET /  (3D 生命体伙伴首页, text/html)",
                "voice_info": "GET /api/voice/info  (STT/TTS/唤醒 引擎可用性)",
                "voice_turn": "POST /api/voice/turn  {\"transcript\"} -> STT→AOS→TTS 整回合 (可传 plan:true 走 ag2 规划)",
                "voice_wake": "POST /api/voice/wake/start|stop · GET /api/voice/wake/status  (常驻 VAD 唤醒)",
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
        # 场景存储的唯一真相源在 companion 模块；http_server 自己的 _SCENES
        # 由 /api/3d/generate 写入，companion 生成的场景在其 _SCENES。两者都查。
        rec = _SCENES.get(sid)
        if rec is None:
            try:
                from core.fabric import companion as _companion
                rec = _companion._SCENES.get(sid)
            except Exception:
                rec = None
        if not rec:
            return self._send_json({"error": "scene not found"}, status=404)
        # 兼容两种存储形态：/api/3d/generate 存 {html,...} 字典；
        # companion 生成直接存 HTML 字符串。
        html = rec["html"] if isinstance(rec, dict) and "html" in rec else rec
        if not isinstance(html, str):
            return self._send_json({"error": "scene 格式异常"}, status=500)
        html = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    # ---- Living Companion Entry ----
    def _serve_living_home(self) -> None:
        try:
            from core.fabric import companion as _companion
            c = _companion.Companion.load("default")
            html = _companion.build_living_home_html(c).encode("utf-8")
        except Exception as e:  # noqa: BLE001
            logger.exception("living home 生成失败")
            return self._send_json({"error": f"living home 失败: {e}"}, status=500)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _get_companion(self) -> None:
        try:
            from core.fabric import companion as _companion
            self._send_json(_companion.get_companion_view("default"))
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": str(e)}, status=500)

    # ---- 人设配置化（谁用谁设）----
    def _get_persona(self, user_id: str) -> None:
        try:
            from core.fabric import persona as _persona
            self._send_json({
                "ok": True,
                "user_id": user_id,
                "persona": _persona.load_persona(user_id),
                # 可编辑字段提示（前端据此渲染表单）
                "editable_fields": [
                    "name", "persona", "body_prompt", "palette_seed",
                    "tts_voice", "greeting", "tone", "catchphrase",
                    "avatar", "mood_emojis",
                ],
                "note": "改 persona 文件或调 PUT 即生效；用户专属覆盖全局默认。",
            })
        except Exception as e:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(e)}, status=500)

    def _put_persona(self, user_id: str, body: dict) -> None:
        if not isinstance(body, dict) or not body:
            return self._send_json(
                {"ok": False, "error": "需要 JSON 人设字段"}, status=400)
        try:
            from core.fabric import companion as _companion
            from core.fabric import persona as _persona
            # 同时更新 Companion 实例（热重载 identity），并写盘人设文件
            c = _companion.Companion.load(user_id)
            if body.get("__reset__"):
                merged = c.reset_persona()
                self._send_json({
                    "ok": True, "user_id": user_id, "persona": merged,
                    "note": "已恢复默认人设。",
                })
                return
            merged = c.set_persona(body)
            self._send_json({
                "ok": True,
                "user_id": user_id,
                "persona": merged,
                "note": "人设已保存并热重载；刷新首页或重新对话即生效。",
            })
        except Exception as e:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(e)}, status=500)

    def _post_companion_message(self, body: dict) -> None:
        text = (body.get("text") or body.get("message") or "").strip()
        if not text:
            return self._send_json({"ok": False, "error": "text required"}, status=400)
        try:
            from core.fabric import companion as _companion
            result = _companion.handle_companion_message(
                text, "default", voice=bool(body.get("voice", False)))
            return self._send_json(result)
        except Exception as e:  # noqa: BLE001 - 永不崩服务
            logger.exception("companion message failed")
            return self._send_json({"ok": False, "error": str(e)})

    # ---- 语音芯粒（方案三）----
    @staticmethod
    def _voice_audio_dir() -> str:
        import os
        return os.environ.get(
            "AOS_VOICE_AUDIO_DIR",
            os.path.join("data", "workspaces", "fabric", "voice_audio"),
        )

    def _get_voice_info(self) -> None:
        try:
            from core.fabric.adapters.stt_adapter import STTAdapter
            from core.fabric.adapters.tts_adapter import TTSAdapter
            stt = STTAdapter()
            tts = TTSAdapter()
            loop = FabricHubHTTPHandler._wake_state.get("loop")
            wake_info = None
            if loop is not None:
                wake_info = {
                    "running": loop.running,
                    "health": loop.health(),
                    "vad_engine": loop.vad_engine_name(),
                    "total_utterances": loop.total_utterances,
                }
            self._send_json({
                "ok": True,
                "stt": {
                    "engine": stt._engine,
                    "live": bool(stt.health()),
                    "detail": stt.health_detail(),
                },
                "tts": {
                    "engine": tts._engine,
                    "live": bool(tts.health()),
                    "detail": tts.health_detail(),
                },
                "wake": wake_info,
                "wake_endpoints": {
                    "start": "POST /api/voice/wake/start",
                    "stop": "POST /api/voice/wake/stop",
                    "status": "GET /api/voice/wake/status",
                },
                "turn_plan": "POST /api/voice/turn 可传 {\"plan\": true} 走 ag2 长任务规划",
                "note": "live=false 时前端自动改用浏览器 Web Speech 兜底；"
                        "无麦克风时唤醒自动退回 🎤 按钮，全链路不崩。",
            })
        except Exception as e:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(e)})

    def _post_voice_stt(self, body: dict) -> None:
        try:
            from core.fabric.adapters.stt_adapter import STTAdapter
            from core.fabric.adapter import InvokeRequest
            payload = {}
            for k in ("transcript", "audio_path", "audio_b64", "audio_suffix"):
                if body.get(k) is not None:
                    payload[k] = body[k]
            r = STTAdapter().invoke(InvokeRequest(capability="voice.stt", payload=payload))
            if not r.ok:
                return self._send_json({"ok": False, "error": r.error}, status=422)
            return self._send_json({"ok": True, **r.data})
        except Exception as e:  # noqa: BLE001
            logger.exception("voice stt failed")
            return self._send_json({"ok": False, "error": str(e)})

    def _post_voice_tts(self, body: dict) -> None:
        text = (body.get("text") or body.get("prompt") or "").strip()
        if not text:
            return self._send_json({"ok": False, "error": "text required"}, status=400)
        try:
            from core.fabric.adapters.tts_adapter import TTSAdapter
            from core.fabric.adapter import InvokeRequest
            payload = {"text": text}
            for k in ("voice", "lang", "language", "speaker_wav"):
                if body.get(k) is not None:
                    payload[k] = body[k]
            r = TTSAdapter().invoke(InvokeRequest(capability="voice.tts", payload=payload))
            if not r.ok:
                return self._send_json({"ok": False, "error": r.error}, status=422)
            return self._send_json({"ok": True, **r.data})
        except Exception as e:  # noqa: BLE001
            logger.exception("voice tts failed")
            return self._send_json({"ok": False, "error": str(e)})

    def _post_voice_turn(self, body: dict) -> None:
        try:
            from core.fabric.voice_chiplet import handle_voice_turn
            force_plan = bool(body.get("plan") or body.get("force_plan"))
            auto_plan = bool(body.get("auto_plan"))
            res = handle_voice_turn(
                transcript=(body.get("transcript") or body.get("text") or ""),
                audio_path=body.get("audio_path", ""),
                audio_b64=body.get("audio_b64", ""),
                user_id=body.get("user_id", "default"),
                barge_window=float(body.get("barge_window", 3.0)),
                force_plan=force_plan,
                auto_plan=auto_plan,
            )
            return self._send_json({
                "ok": res.ok,
                "user_text": res.user_text,
                "reply": res.reply,
                "audio_url": res.audio_url,
                "tts_engine": res.tts_engine,
                "mood": res.mood,
                "planner_used": res.planner_used,
                "scene_id": res.scene_id,
                "state": res.state,
                "error": res.error,
            })
        except Exception as e:  # noqa: BLE001 - 永不崩服务
            logger.exception("voice turn failed")
            return self._send_json({"ok": False, "error": str(e)})

    # ---- 常驻语音唤醒（VAD 监听）----
    _wake_state: dict = {"loop": None, "handler": None, "last": None, "pipeline": None}

    def _get_wake_loop(self):
        st = FabricHubHTTPHandler._wake_state
        if st["loop"] is None:
            try:
                from core.fabric.voice_wake import VoiceWakeLoop, make_wake_turn_handler
                from core.fabric.voice_chiplet import VoicePipeline
                pipe = VoicePipeline(user_id="wake")
                handler, last = make_wake_turn_handler(pipeline=pipe, user_id="wake")
                loop = VoiceWakeLoop(on_utterance=handler)
                st.update(loop=loop, handler=handler, last=last, pipeline=pipe)
            except Exception as e:  # noqa: BLE001
                logger.exception("init wake loop failed")
                return None
        return st["loop"]

    def _post_voice_wake_start(self) -> None:
        loop = self._get_wake_loop()
        if loop is None:
            return self._send_json({"ok": False, "error": "唤醒模块初始化失败"}, status=500)
        if not loop.health():
            return self._send_json({
                "ok": False,
                "running": False,
                "health": False,
                "vad_engine": loop.vad_engine_name(),
                "error": loop.last_error or "无麦克风/输入设备；请用浏览器 🎤 按钮",
            }, status=409)
        ok = loop.start()
        return self._send_json({
            "ok": bool(ok),
            "running": loop.running,
            "health": True,
            "vad_engine": loop.vad_engine_name(),
            "sample_rate": loop.sample_rate,
            "note": "常驻监听已开启；说话即自动触发 STT→AOS→TTS 整回合（0.3s 级响应）。",
        })

    def _post_voice_wake_stop(self) -> None:
        loop = FabricHubHTTPHandler._wake_state["loop"]
        if loop is not None:
            loop.stop()
        return self._send_json({"ok": True, "running": False})

    def _get_voice_wake_status(self) -> None:
        st = FabricHubHTTPHandler._wake_state
        loop = st["loop"]
        if loop is None:
            return self._send_json({
                "ok": True, "running": False, "health": False,
                "vad_engine": None,
                "last_result": None,
                "note": "尚未初始化；POST /api/voice/wake/start 触发（需麦克风）。",
            })
        return self._send_json({
            "ok": True,
            "running": loop.running,
            "health": loop.health(),
            "vad_engine": loop.vad_engine_name(),
            "total_utterances": loop.total_utterances,
            "last_result": st.get("last"),
        })

    # ---- LNN（液态神经网络时间序列推理）----
    def _get_lnn_info(self) -> None:
        try:
            from core.fabric.adapters.lnn_adapter import LNNAdapter
            from core.fabric.adapters.lfm_adapter import LFMAdapter
            lnn = LNNAdapter()
            lfm = LFMAdapter()
            self._send_json({
                "ok": True,
                "lnn": {
                    "engine": lnn._engine,
                    "live": bool(lnn.health()),
                    "detail": lnn.health_detail(),
                },
                "lfm2": {
                    "engine": lfm._engine,
                    "model": lfm._model,
                    "live": bool(lfm.health()),
                    "detail": lfm.health_detail(),
                },
                "note": "LNN 擅长时间序列/动态适应（本地零依赖）；LFM2 为 inference.llm 的"
                        "轻量供给方，权重未下载时自动退回其它 live LLM（高低搭配）。",
            })
        except Exception as e:  # noqa: BLE001
            self._send_json({"ok": False, "error": str(e)})

    def _post_lnn_predict(self, body: dict) -> None:
        try:
            from core.fabric.adapters.lnn_adapter import LNNAdapter
            from core.fabric.adapter import InvokeRequest
            payload = {}
            for k in ("series", "horizon", "demo", "epochs"):
                if body.get(k) is not None:
                    payload[k] = body[k]
            r = LNNAdapter().invoke(InvokeRequest(capability="inference.lnn", payload=payload))
            if not r.ok:
                return self._send_json({"ok": False, "error": r.error}, status=422)
            return self._send_json({"ok": True, **r.data})
        except Exception as e:  # noqa: BLE001
            logger.exception("lnn predict failed")
            return self._send_json({"ok": False, "error": str(e)})

    def _serve_voice_audio(self, fid: str) -> None:
        # 防目录穿越：只用 basename
        import os
        fname = os.path.basename(fid)
        if ".." in fname or "/" in fname or "\\" in fname:
            return self._send_json({"error": "bad id"}, status=400)
        fpath = os.path.join(self._voice_audio_dir(), fname)
        if not os.path.isfile(fpath):
            return self._send_json({"error": "audio not found"}, status=404)
        ctype = "audio/mpeg" if fname.lower().endswith(".mp3") else "audio/wav"
        data = open(fpath, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)


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
