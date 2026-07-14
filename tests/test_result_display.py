"""交付结果展示（artifacts）测试。

覆盖：
- companion 返回含 artifacts 列表（默认空，task 意图产出真实卡片）。
- task 意图识别，且不被 3D 意图吞掉。
- _run_agentic_task 真实执行路径（fake 适配器注入）与诚实降级路径。
- 首页 HTML 含产物面板（#artifacts / renderArtifacts / 收起）。
- 语音链路透传：VoiceTurnResult.artifacts → http_server._post_voice_turn 返回。
"""

import os
import tempfile

import pytest


@pytest.fixture
def companion_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "companion")
    monkeypatch.setenv("AOS_COMPANION_DIR", d)
    return d


def test_handle_returns_artifacts_list(companion_dir):
    from core.fabric import companion as C
    res = C.handle_companion_message("你好", "u1")
    assert "artifacts" in res
    assert isinstance(res["artifacts"], list)


def test_task_intent_detection(companion_dir):
    from core.fabric import companion as C
    c = C.Companion.load("u2")
    assert c.route_intent("写个Python算斐波那契")["kind"] == "task"
    assert c.route_intent("跑一下这段代码")["kind"] == "task"
    assert c.route_intent("做一个连连看小游戏")["kind"] == "task"
    # 3D 意图不应被 task 吞掉
    assert c.route_intent("做个宇宙星河场景")["kind"] == "3d"
    # 普通聊天不是 task
    assert c.route_intent("今天天气怎么样")["kind"] == "chat"


def test_task_artifact_real_run(companion_dir, monkeypatch):
    import core.fabric.adapters.code_execution_adapter as ce_mod
    from core.fabric.adapter import InvokeResult

    class FakeExec:
        def __init__(self, *a, **k):
            pass

        def invoke(self, req):
            return InvokeResult(
                ok=True,
                data={"content": "1\n1\n2\n3", "output": "1\n1\n2\n3",
                      "language": "python", "engine": "sandbox"},
            )

    monkeypatch.setattr(ce_mod, "CodeExecutionAdapter", FakeExec)
    from core.fabric import companion as C
    text = "```python\nprint(1)\n```"
    reply, arts = C._run_agentic_task(text)
    types = [a["type"] for a in arts]
    assert "code" in types and "text" in types
    # 经过完整 handle 也带 artifacts（用会触发 task 意图的指令）
    res = C.handle_companion_message("执行这段代码：```python\nprint(1)\n```", "u3")
    assert any(a["type"] == "code" for a in res["artifacts"])


def test_task_artifact_honest_degrade(companion_dir, monkeypatch):
    import core.fabric.adapters.code_execution_adapter as ce_mod

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("no sandbox available")

    monkeypatch.setattr(ce_mod, "CodeExecutionAdapter", Boom)
    from core.fabric import companion as C
    reply, arts = C._run_agentic_task("写个Python算斐波那契")
    assert any(a.get("level") == "warn" for a in arts)
    assert "代码执行环境还没准备好" in reply
    # 不应谎报成功
    assert not any(a["type"] == "code" for a in arts)


def test_living_home_has_artifacts_panel(companion_dir):
    from core.fabric import companion as C
    html = C.build_living_home_html(C.Companion.load("u4"))
    for tok in ['id="artifacts"', "renderArtifacts", "artClose",
                "#artifacts.show", "artList"]:
        assert tok in html, tok


def test_voice_turn_result_carries_artifacts():
    from core.fabric.voice_chiplet import VoiceTurnResult
    r = VoiceTurnResult(ok=True, reply="x",
                        artifacts=[{"type": "code", "content": "print(1)"}])
    assert r.artifacts and r.artifacts[0]["type"] == "code"


def test_http_voice_turn_passes_artifacts(monkeypatch):
    import core.fabric.http_server as hs
    import core.fabric.voice_chiplet as vc
    from core.fabric.voice_chiplet import VoiceTurnResult

    captured = {}

    def fake_handle(transcript="", audio_path="", audio_b64="", audio_suffix="wav",
                    force_plan=False, user_id="default", barge_window=3.0,
                    auto_plan=False):
        return VoiceTurnResult(
            ok=True, user_text=transcript, reply="done",
            artifacts=[{"type": "code", "content": "x"}])

    monkeypatch.setattr(vc, "handle_voice_turn", fake_handle)
    h = hs.FabricHubHTTPHandler.__new__(hs.FabricHubHTTPHandler)
    h._send_json = lambda obj, status=200: captured.update(status=status, obj=obj)
    h._post_voice_turn({"transcript": "写个代码", "user_id": "default"})
    assert captured["obj"]["artifacts"] == [{"type": "code", "content": "x"}]
