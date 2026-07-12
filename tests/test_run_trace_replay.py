"""失败回放回归（炼化自 FetchSandbox 思路）。

FetchSandbox 的核心是"记录真实故障场景，回归时自动重放"。这里把 AOS 自己真实
跑出来的 run trace 存成夹具（tests/fixtures/），重放时断言诚实性不变量：
  1) 搜索成功步必须带真实、非空内容（证明不是假搜）；
  2) 出图步成功必须带真实 URL（不是占位/空）；
  3) 任意失败步必须带诚实 error 文本，且不得用空成功掩盖；
  4) 上游失败不能让下游"假成功"出图/出记忆（失败被隔离，前两步仍真实）。
"""
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures")

RUNS = [
    "run_baidu_channel_access.json",
    "run_anysearch_memory.json",
]


def _load(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return json.load(f)


def _trace(run):
    return run["execution"]["trace"]


def _find(trace, cap):
    return next((s for s in trace if s["capability"] == cap), None)


@pytest.mark.parametrize("fix", RUNS)
def test_search_step_is_real_not_fake(fix):
    run = _load(fix)
    s = _find(_trace(run), "web.search")
    assert s is not None and s["ok"] is True
    out = s["out"]
    assert out.get("engine") in ("baidu", "anysearch", "bing", "duckduckgo", "jina")
    assert out.get("count") not in (None, "0", 0, "")
    assert (out.get("content") or "").strip() != ""


@pytest.mark.parametrize("fix", RUNS)
def test_image_step_produced_real_url(fix):
    run = _load(fix)
    s = _find(_trace(run), "media.image")
    assert s is not None and s["ok"] is True
    out = s["out"]
    assert "agnes-ai.space/images" in (out.get("images") or "")


@pytest.mark.parametrize("fix", RUNS)
def test_failed_steps_are_honest_no_fake_success(fix):
    run = _load(fix)
    for s in _trace(run):
        if not s["ok"]:
            # 失败必须带 error 文本（不得用空成功掩盖）
            assert (s.get("error") or "").strip() != ""
        else:
            # 成功步输出不得为空
            assert s.get("out") not in (None, {}, "")


@pytest.mark.parametrize("fix,third", [
    ("run_baidu_channel_access.json", "channel.access"),
    ("run_anysearch_memory.json", "memory.semantic"),
])
def test_edge_step_failure_is_contained(fix, third):
    """第3步（channel/memory）失败不应污染前两步：前两步仍真实成功。"""
    run = _load(fix)
    trace = _trace(run)
    assert _find(trace, "web.search")["ok"] is True
    assert _find(trace, "media.image")["ok"] is True
    assert _find(trace, third)["ok"] is False
