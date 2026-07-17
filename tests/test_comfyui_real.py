"""ComfyUI 接电真跑测试 —— 不 mock 业务逻辑，只 mock「外部 ComfyUI 服务」本身。

用 stdlib http.server 起一个假 ComfyUI（/system_info /prompt /history /config），
真实走完 AOS 侧全链路：adapter.health 探活 → invoke 一句话 → 自动推断 txt2img →
真 POST /prompt → 真轮询 /history → 真解析 output_path。验证的是「AOS 接电正确」，
而非「ComfyUI 能出图」（出图那步必须你主机真起服务，沙箱无 GPU/无网）。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

RECEIVED_PROMPTS = []


class _Handler(BaseHTTPRequestHandler):
    """假 ComfyUI：把收到的 workflow 记下来，回标准成功响应。"""
    output_dir = "./output"
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[-1]
            self._json(200, {pid: {"outputs": {"9": {"images": [{"filename": "aos_txt2img_0001.png"}]}}}})
        elif self.path.startswith("/system_info"):
            self._json(200, {"system": {"devices": []}})
        elif self.path.startswith("/config"):
            self._json(200, {"output_dir": self.output_dir})
        else:
            self._json(404, {})

    def do_POST(self):
        if self.path == "/prompt":
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n))
            RECEIVED_PROMPTS.append(data["prompt"])
            self._json(200, {"prompt_id": f"p{len(RECEIVED_PROMPTS)}"})
        else:
            self._json(404, {})


@pytest.fixture
def fake_comfyui(tmp_path):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    _Handler.output_dir = str(tmp_path / "out")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    old = os.environ.get("COMFYUI_BASE_URL")
    os.environ["COMFYUI_BASE_URL"] = url
    yield url
    srv.shutdown()
    if old is None:
        os.environ.pop("COMFYUI_BASE_URL", None)
    else:
        os.environ["COMFYUI_BASE_URL"] = old


def _invoke(prompt_payload: dict, capability: str = "media.image"):
    from core.fabric.adapter import InvokeRequest
    from kernel.plugins.comfyui_adapter import ComfyUIAdapter
    return ComfyUIAdapter().invoke(InvokeRequest(capability=capability, payload=prompt_payload))


def test_health_probe_true(fake_comfyui):
    """adapter.health() 真实探 /system_info，服务在 → True。"""
    from kernel.plugins.comfyui_adapter import ComfyUIAdapter
    assert ComfyUIAdapter().health() is True


def test_one_shot_txt2img_real(fake_comfyui):
    """一句话 prompt → 自动 txt2img → 真提交假 ComfyUI → 真解析 output_path。"""
    RECEIVED_PROMPTS.clear()
    res = _invoke({"prompt": "一只在雨中的猫"})
    assert res.ok is True
    assert res.data["action"] == "txt2img"
    assert res.data["output_path"] and "aos_txt2img" in res.data["output_path"]
    # 真跑坑已修：提交给 ComfyUI 的 workflow seed 必须非负
    assert RECEIVED_PROMPTS, "ComfyUI 未收到 /prompt 提交"
    wf = RECEIVED_PROMPTS[0]
    seed = wf["3"]["inputs"]["seed"]
    assert isinstance(seed, int) and seed >= 0, f"seed 仍为负/非法: {seed}"


def test_infer_action_img2vid(fake_comfyui):
    """给图片路径 → 自动推断 img2vid（不要求用户指定 action）。"""
    res = _invoke({"image_path": "x.png", "prompt": "让这张图动起来"})
    assert res.data["action"] == "img2vid"


def test_via_fabric_hub_route(fake_comfyui):
    """经真实 FabricHub.route 一句话出图（验证新栈路由真正落到 comfyui）。

    构造 FabricHub 较重（~2min，会预热重型依赖），单独跑；若构造失败则 skip
    不伪造成功。
    """
    try:
        from kernel.plugins.fabric_hub import FabricHub
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"FabricHub 不可用: {e}")

    hub = FabricHub()
    res = hub.route("media.image", {"prompt": "雪山下的小镇"})
    # 本地 ComfyUI 是 high 档，应优先于云端 agnes 被选中
    assert res.ok is True, f"route 失败: {res.error}"
    assert res.engine_id == "comfyui", f"未路由到 comfyui: {res.engine_id}"
    assert res.data and "aos_txt2img" in (res.data.get("output_path") or "")
