"""OpenMAIC 桥接（edu.course_gen 教育能力芯粒）测试。

不依赖真实 OpenMAIC 服务：用 unittest.mock 替换 urllib.request.urlopen，
覆盖「诚实降级」与「成功路径」两条主线，守护宪法 §6（绝不伪造成功）。

运行环境：AOS 全套依赖装在主机 Python
（C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe，
或 aos venv）；直接 `python tests/test_openmaic_bridge.py` 或 `pytest tests/ -q`。
"""
import json
import os
import sys
import urllib.error
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from kernel.plugins.openmaic_bridge import OpenMAICBridge, generate_course  # noqa: E402


class _FakeResp:
    """模拟 urllib 成功响应。"""

    def __init__(self, status: int, payload: dict):
        self._status = status
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# 共享状态：当前 scenario 决定 urlopen 返回什么；每个测试切换。
_STATE = {"scenario": "ok"}


def _fake_urlopen(req, timeout=None):
    url = req.get_full_url() if hasattr(req, "get_full_url") else getattr(req, "full_url", str(req))
    method = getattr(req, "method", None) or "GET"
    s = _STATE["scenario"]
    if s == "unreachable":
        raise urllib.error.URLError("Simulated: OpenMAIC unreachable")
    if "/api/health" in url:
        return _FakeResp(200, {"success": True, "status": "ok",
                               "version": "0.3.0", "capabilities": ["course"]})
    if "/api/generate-classroom" in url and method == "POST":
        return _FakeResp(202, {"success": True, "jobId": "job_1", "status": "queued",
                                "step": "init", "message": "ok",
                                "pollUrl": url + "/job_1", "pollIntervalMs": 5000})
    if "/api/generate-classroom/job_1" in url:
        return _FakeResp(200, {"success": True, "status": "succeeded", "done": True,
                                "step": "done", "progress": 100, "message": "done",
                                "scenesGenerated": 3, "totalScenes": 3,
                                "result": {"id": "course_1",
                                           "url": "http://localhost:3000/c/course_1",
                                           "scenesCount": 3,
                                           "stage": {"name": "青少年护眼科普课"}},
                                "error": None})
    return _FakeResp(404, {"success": False, "error": "not found"})


def _with(scenario: str):
    """切到指定 scenario 并 patch urlopen。"""
    _STATE["scenario"] = scenario
    return patch("urllib.request.urlopen", _fake_urlopen)


# ── 桥接层：成功路径 ──────────────────────────────────────────────
def test_full_flow_success():
    """提交+轮询至 done，结构化字段正确解包。"""
    with _with("ok"):
        out = OpenMAICBridge("http://localhost:3000").generate_course(
            "青少年护眼科普课", poll_interval=0,
        )
    assert out["ok"] is True
    assert out["job_id"] == "job_1"
    assert out["course_id"] == "course_1"
    assert out["url"] == "http://localhost:3000/c/course_1"
    assert out["scenes_count"] == 3
    assert out["title"] == "青少年护眼科普课"


def test_health_ok_parses():
    """健康探测成功：解析 version/capabilities。"""
    with _with("ok"):
        h = OpenMAICBridge("http://localhost:3000").health()
    assert h["ok"] is True
    assert h["version"] == "0.3.0"
    assert h["capabilities"] == ["course"]


# ── 桥接层：诚实降级（宪法 §6）────────────────────────────────────
def test_empty_requirement_rejected():
    """requirement 为空：本地即拒，不触网。"""
    out = OpenMAICBridge("http://localhost:3000").generate_course("")
    assert out["ok"] is False
    assert "空" in (out["error"] or "")


def test_health_unreachable_honest():
    """健康探测不可达：如实 ok=False，带错误，绝不说健康。"""
    with _with("unreachable"):
        h = OpenMAICBridge("http://unreachable.invalid:3000").health()
    assert h["ok"] is False
    assert h.get("error")


def test_generate_unreachable_honest_failure():
    """课程生成不可达：如实 ok=False（HTTP 级别失败），绝不伪造成功。"""
    with _with("unreachable"):
        out = OpenMAICBridge("http://unreachable.invalid:3000").generate_course(
            "护眼科普课", poll_interval=0,
        )
    assert out["ok"] is False
    assert "HTTP" in (out["error"] or "")


# ── 注册/编排消费层 ──────────────────────────────────────────────
def test_factory_disabled_returns_none():
    """未配置 AOS_OPENMAIC_URL：工厂静默返回 None（opt-in 核心纪律）。"""
    from kernel.plugins.extension import _openmaic_factory
    os.environ.pop("AOS_OPENMAIC_URL", None)
    assert _openmaic_factory() is None


def test_factory_enabled_returns_bridge():
    """配置 AOS_OPENMAIC_URL：工厂返回真实 OpenMAICBridge 实例。"""
    from kernel.plugins.extension import _openmaic_factory, get_extension
    os.environ["AOS_OPENMAIC_URL"] = "http://localhost:3000"
    try:
        inst = _openmaic_factory()
        assert isinstance(inst, OpenMAICBridge)
        # get_extension 经 env_gate 也应启用
        assert get_extension("openmaic") is not None
    finally:
        os.environ.pop("AOS_OPENMAIC_URL", None)


def test_module_generate_not_enabled():
    """模块级入口在未启用时返回 InvokeResult.ok=False 且点名未启用。"""
    os.environ.pop("AOS_OPENMAIC_URL", None)
    from kernel.plugins.extension import get_extension
    assert get_extension("openmaic") is None
    res = generate_course({"requirement": "护眼科普课"})
    assert res.ok is False
    assert "未启用" in (res.error or "")


if __name__ == "__main__":
    test_full_flow_success()
    test_health_ok_parses()
    test_empty_requirement_rejected()
    test_health_unreachable_honest()
    test_generate_unreachable_honest_failure()
    test_factory_disabled_returns_none()
    test_factory_enabled_returns_bridge()
    test_module_generate_not_enabled()
    print("ALL OPENMAIC_BRIDGE TESTS PASSED")
