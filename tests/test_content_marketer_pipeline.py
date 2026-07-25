"""content_marketer_adapter：promote_pipeline / short_drama / identity_anchors 真实运行验证。

不依赖真 LLM / 真媒体引擎：用最小假 route_fn 喂确定性数据，验证
① 代码改动真实（adapter 真跑出多阶段结果，不静默失败）
② 闸门逻辑真实（reviewer 可在任意阶段挡停）
③ short_drama 能力已注册、pipeline 分支可由 invoke 触发
④ identity_anchors 真被透传到 media.video 调用
符合 §0.7 诚实纪律：只验适配层（layer ①②），不谎报端到端生成闭环。
"""
from __future__ import annotations

import os
import tempfile

from core.fabric.adapter import InvokeRequest, InvokeResult
from core.fabric.adapters.content_marketer_adapter import (
    ContentMarketerAdapter,
    PromoteResult,
)
from core.fabric.capability import Capability


class _FakeRoute:
    """最小 route_fn：按 cap 返回确定性假数据，记录调用轨迹。

    media.video 造一个真实存在的本地文件，让适配器的 _localize_video
    通过（避免「桩返回不存在路径 → 被当失败」的假红）。
    """

    def __init__(self):
        self.calls: list[tuple] = []
        self._tmp = tempfile.mkdtemp()

    def __call__(self, cap: str, payload: dict):
        self.calls.append((cap, dict(payload)))
        if cap == "web.search":
            return {"results": [{"title": "护眼科普", "url": "https://e.x/1"}]}
        if cap == "inference.llm":
            # 返回够长的脚本（>50 字），让 _write_script 走 LLM 分支而非模板降级
            return {"content": "分镜一：小明在书房看书。\n分镜二：妈妈提醒注意坐姿。\n分镜三：戴上护眼平板。"}
        if cap == "media.video":
            p = os.path.join(self._tmp, "fake.mp4")
            open(p, "wb").close()
            return {"output_path": p, "duration": 30}
        if cap == "media.audio":
            return {"audio_path": os.path.join(self._tmp, "fake.mp3")}
        if cap == "content.distribute":
            return {"platforms": ["douyin"]}
        return None


def _adapter() -> ContentMarketerAdapter:
    return ContentMarketerAdapter(route_fn=_FakeRoute())


def test_health_and_capabilities():
    a = _adapter()
    assert a.health() is True
    names = {c.value for c in a.advertise_capabilities()}
    assert "content.marketing_video" in names
    assert "content.short_drama" in names  # waoowaoo [C] 已注册


def test_promote_pipeline_runs_all_six_stages():
    a = _adapter()
    r = a.promote_pipeline(
        "青少年护眼科普",
        identity_anchors={"角色": "小明", "场景": "书房"},
    )
    assert isinstance(r, PromoteResult)
    assert r.ok is True
    assert r.stages_done == ["选题", "素材", "分镜", "配音", "成片", "分发"]
    assert r.stopped_at == ""
    # identity_anchors 真被透传到 media.video 调用（waoowaoo [B]）
    video_calls = [p for c, p in a._route_fn.calls if c == "media.video"]
    assert video_calls, "成片阶段应调用 media.video"
    assert video_calls[0]["identity_anchors"] == {"角色": "小明", "场景": "书房"}


def test_reviewer_can_stop_pipeline_at_any_stage():
    a = _adapter()

    def stop_at_script(stage, artifact):
        return stage != "分镜"

    r = a.promote_pipeline("护眼科普", reviewer=stop_at_script)
    assert r.stopped_at == "分镜"
    assert "成片" not in r.stages_done
    assert r.ok is False


def test_short_drama_prompt_variant():
    fr = _FakeRoute()
    a = ContentMarketerAdapter(route_fn=fr)
    a.promote_pipeline("护眼短剧", short_drama=True)
    llm_calls = [p for c, p in fr.calls if c == "inference.llm"]
    assert llm_calls, "短剧模式应触发 LLM 写脚本"
    assert "短剧" in llm_calls[0]["prompt"]


def test_invoke_pipeline_branch():
    a = _adapter()
    res = a.invoke(InvokeRequest(
        capability=Capability.CONTENT_MARKETING_VIDEO,
        payload={"topic": "护眼", "pipeline": True},
    ))
    assert isinstance(res, InvokeResult)
    assert res.ok is True
    assert "成片" in res.data["stages_done"]
