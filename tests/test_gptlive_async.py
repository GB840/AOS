"""GPT-Live 思想落地测试：前台不阻塞 + 后台异步 plan + 结果轮询回填。

核心验证：
1. 语音回合在 plan 时立即返回前台短反馈 + task_id（不阻塞等后台）。
2. 后台线程跑完，get_task_result 返回 done 结果（含 artifacts）。
3. HTTP 层：/api/voice/turn 返回 task_id；GET /api/voice/task/{id} 轮询返回后台结果。
"""

import time

import pytest

from core.fabric import voice_chiplet as VC
from core.fabric.voice_chiplet import VoicePipeline, VoiceTurnResult


def _fake_planner(text):
    return {
        "reply": "后台帮你把 A→B→C 三步跑完了。",
        "planner_used": "ag2",
        "artifacts": [{"type": "text", "content": "做了：A、B、C"}],
        "scene_id": None,
    }


def test_front_desk_not_blocking():
    """plan 时前台立即返回短反馈 + task_id，不等后台。"""
    # 注入即时 tts_fn，隔离出「plan 异步不阻塞」本身（TTS 首载耗时不计入前台判定）
    pipe = VoicePipeline(
        planner_fn=_fake_planner,
        tts_fn=lambda text: {"text": text, "engine": "web_speech"},
    )
    t0 = time.time()
    res = pipe.handle_voice_turn(transcript="做一个计划：先A然后B", force_plan=True)
    elapsed = time.time() - t0
    # 立刻返回（后台在另一线程跑，不计时）
    assert elapsed < 1.0, f"前台不应阻塞，实际耗时 {elapsed:.2f}s"
    assert res.task_id and res.task_id.startswith("vt_")
    assert res.reply in VoicePipeline._FRONT_ACKS
    assert res.artifacts is None  # 前台不携带后台结果


def test_background_task_completes_with_artifacts():
    """后台线程跑完，结果含 reply/planner_used/artifacts。"""
    pipe = VoicePipeline(planner_fn=_fake_planner)
    res = pipe.handle_voice_turn(transcript="安排一下：A然后B", force_plan=True)
    tid = res.task_id
    # 轮询直到 done
    for _ in range(60):
        r = VoicePipeline.get_task_result(tid)
        if r and r.get("status") in ("done", "error"):
            break
        time.sleep(0.05)
    assert r is not None and r["status"] == "done"
    assert r["reply"].startswith("后台")
    assert r["planner_used"] == "ag2"
    assert r["artifacts"][0]["content"] == "做了：A、B、C"


def test_no_plan_stays_sync():
    """非 plan 意图仍是同步返回（走 respond_fn），不带 task_id。"""

    def respond(text):
        return {"reply": "普通回复", "mood": "calm"}

    pipe = VoicePipeline(respond_fn=respond)
    res = pipe.handle_voice_turn(transcript="你好", force_plan=False)
    assert res.task_id is None
    assert res.reply == "普通回复"


def test_http_task_roundtrip(monkeypatch):
    """HTTP：/api/voice/turn 返回 task_id；GET /api/voice/task/{id} 轮询返回后台结果。"""
    from core.fabric import http_server as HS

    monkeypatch.setattr(
        VC, "handle_voice_turn",
        lambda **kw: VoiceTurnResult(
            ok=True, user_text=kw.get("transcript", ""),
            reply="前台反馈", task_id="vt_test123"),
    )
    monkeypatch.setattr(
        VoicePipeline, "get_task_result",
        classmethod(lambda cls, tid: None if tid == "vt_nope" else {
            "status": "done", "reply": "后台做了",
            "planner_used": "ag2",
            "artifacts": [{"type": "text", "content": "x"}],
        }),
    )

    h = HS.FabricHubHTTPHandler.__new__(HS.FabricHubHTTPHandler)
    captured = {}
    h._send_json = lambda obj, status=200: captured.update(status=status, obj=obj)

    # turn
    h._post_voice_turn({"transcript": "安排一下", "plan": True})
    assert captured["obj"]["task_id"] == "vt_test123"
    assert captured["obj"]["reply"] == "前台反馈"

    # task query
    h._get_voice_task("vt_test123")
    assert captured["obj"]["ok"] is True
    assert captured["obj"]["status"] == "done"
    assert captured["obj"]["reply"] == "后台做了"
    assert captured["obj"]["artifacts"][0]["content"] == "x"

    # unknown task
    h._get_voice_task("vt_nope")
    assert captured["obj"]["ok"] is False
