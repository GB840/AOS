"""Remotion 适配器（③ Tier1 缺口）真跑验证。

覆盖：
- 能力声明 video.remotion
- 诚实降级：health=False / 缺参数 / 项目不存在 → ok=False 不谎报
- 真渲染路径（mock subprocess）→ ok=True 且产出文件
- API 端点：/health + /render（mock 适配器，不依赖真 Remotion CLI）

用法：
  PYTHONPATH=D:/AOS/src <py> verify_remotion.py
"""
import os
import sys
import tempfile

try:
    from core.fabric.adapter import InvokeRequest, InvokeResult, Capability
    from core.fabric.adapters.remotion_adapter import RemotionAdapter
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except Exception as e:  # noqa: BLE001
    print(f"IMPORT FAIL: {e}")
    sys.exit(2)

_passed = 0
_failed = 0


def check(cond, msg):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✓ {msg}")
    else:
        _failed += 1
        print(f"  ✗ {msg}")


def test_adapter():
    print("[适配器]")
    a = RemotionAdapter()
    check(a.advertise_capabilities() == ["video.remotion"], "声明能力 video.remotion")
    check(isinstance(a.health(), bool), "health() 返回 bool")

    # 缺 project_dir
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO,
                               payload={"composition_id": "Main"}))
    check(r.ok is False and "project_dir" in r.error, "缺 project_dir → ok=False（诚实）")

    # 缺 composition_id
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO,
                               payload={"project_dir": "/tmp/x"}))
    check(r.ok is False and "composition_id" in r.error, "缺 composition_id → ok=False（诚实）")

    # 项目目录不存在
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO,
                               payload={"project_dir": "/no/such/dir", "composition_id": "Main"}))
    check(r.ok is False and "不存在" in r.error, "project_dir 不存在 → ok=False（诚实）")


class _FakeProc:
    returncode = 0
    stderr = ""


def test_render_success(tmp):
    print("[渲染成功路径（mock subprocess）]")
    a = RemotionAdapter()
    out = os.path.join(tmp, "out.mp4")
    # 构造一个真存在的 entry 文件 + project_dir
    proj = os.path.join(tmp, "proj")
    os.makedirs(os.path.join(proj, "src"), exist_ok=True)
    open(os.path.join(proj, "src", "index.tsx"), "w").write("// remotion entry")

    captured = {}

    def fake_run(cmd, cwd, timeout, **kw):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        # 模拟 Remotion 写出输出文件
        open(out, "w").write("fake mp4")
        return _FakeProc()

    a._run_render = fake_run
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO, payload={
        "project_dir": proj,
        "composition_id": "MyComp",
        "props": {"title": "测试", "data": [1, 2, 3]},
        "output": out,
    }))
    check(r.ok is True, "mock 渲染成功 → ok=True")
    check(r.data.get("output") == os.path.abspath(out), "返回 output 绝对路径")
    check(os.path.isfile(out), "输出文件真实生成")
    check(captured["cmd"][:3] == ["npx", "remotion", "render"], "命令以 npx remotion render 开头")
    check("--props=" in " ".join(captured["cmd"]), "props 透传给 Remotion CLI")
    check(captured["cwd"] == proj, "cwd 设为 project_dir")


def test_render_fail(tmp):
    print("[渲染失败路径（mock subprocess 非零退出）]")
    a = RemotionAdapter()
    out = os.path.join(tmp, "fail.mp4")
    proj = os.path.join(tmp, "proj2")
    os.makedirs(os.path.join(proj, "src"), exist_ok=True)
    open(os.path.join(proj, "src", "index.tsx"), "w").write("// x")

    class _BadProc:
        returncode = 1
        stderr = "Error: composition not found"

    def fake_run(*a, **k):
        return _BadProc()

    a._run_render = fake_run
    r = a.invoke(InvokeRequest(capability=Capability.MEDIA_VIDEO, payload={
        "project_dir": proj, "composition_id": "NoSuch", "output": out,
    }))
    check(r.ok is False and "渲染失败" in r.error, "Remotion 报错 → ok=False 诚实返回")


def test_api():
    print("[API 端点]")
    app = FastAPI()
    from api.video_api import router

    # mock 适配器，避免依赖真 Remotion CLI
    class FakeAdapter:
        def health_detail(self):
            return {"engine_id": "remotion", "available": True, "npx_path": "/usr/bin/npx",
                    "remotion_path": None, "note": "mock"}
        def invoke(self, req):
            return InvokeResult(ok=True, data={"output": "/tmp/x.mp4",
                                              "composition_id": "C", "size_mb": 1.2},
                                engine_id="remotion")

    import api.video_api as va
    va._get_adapter = lambda: FakeAdapter()
    app.include_router(router)
    c = TestClient(app)

    h = c.get("/api/video/remotion/health")
    check(h.status_code == 200 and h.json()["available"] is True, "/health 200 + available=True")

    body = {"project_dir": "/p", "composition_id": "C", "props": {"a": 1}}
    rp = c.post("/api/video/remotion/render", json=body)
    check(rp.status_code == 200 and rp.json().get("output") == "/tmp/x.mp4",
          "/render 200 + 返回 output（mock 适配器）")


if __name__ == "__main__":
    tmp = tempfile.mkdtemp(prefix="aos_remotion_")
    try:
        test_adapter()
        test_render_success(tmp)
        test_render_fail(tmp)
        test_api()
    finally:
        pass
    print(f"\n结果: {_passed} 通过 / {_failed} 失败")
    sys.exit(1 if _failed else 0)
