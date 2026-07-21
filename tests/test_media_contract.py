"""media 平面返回契约统一测试（P1 收口）。

验证：
- normalize_media_data 把四态原生 data 投影成 url/output/output_path 三键并存
- extract_media_url 兼容 url→output→output_path 优先级
- content_marketer 消费方在 media-gen(url 形状) 下不再静默失败
- content_marketer 在 video-maker(output 形状) 下同样能拿到本地路径
"""
from __future__ import annotations

from core.fabric.adapter import (
    InvokeResult,
    extract_media_url,
    normalize_media_data,
)
from core.fabric.adapters.content_marketer_adapter import ContentMarketerAdapter


# ---- normalize_media_data：四态投影 ----
def test_normalize_video_maker_shape():
    d = normalize_media_data({"output": "/a/b.mp4"})
    assert d["url"] == "/a/b.mp4"
    assert d["output"] == "/a/b.mp4"
    assert d["output_path"] == "/a/b.mp4"


def test_normalize_comfyui_shape():
    d = normalize_media_data({"output_path": "/c/d.png", "mode": "txt2img"})
    assert d["url"] == "/c/d.png"
    assert d["output_path"] == "/c/d.png"
    # 原始字段保留，下游按需读任意键
    assert d["mode"] == "txt2img"


def test_normalize_media_gen_shape_keeps_url():
    d = normalize_media_data({"url": "https://x/y.png", "model": "cogview"})
    assert d["url"] == "https://x/y.png"
    assert d["output"] == "https://x/y.png"
    assert d["model"] == "cogview"


def test_normalize_data_list_nested_url():
    d = normalize_media_data({"data": [{"url": "https://x/z.png"}]})
    assert d["url"] == "https://x/z.png"


def test_normalize_passthrough_existing_url():
    d = normalize_media_data({"url": "https://x/y.png", "output": "/local.png"})
    # url 已存在则保留，不被本地路径覆盖
    assert d["url"] == "https://x/y.png"
    assert d["output"] == "/local.png"


# ---- extract_media_url：优先级 ----
def test_extract_prefers_url():
    assert extract_media_url({"url": "https://a", "output": "/b"}) == "https://a"


def test_extract_falls_back_to_output():
    assert extract_media_url({"output": "/b.mp4"}) == "/b.mp4"


def test_extract_falls_back_to_output_path():
    assert extract_media_url({"output_path": "/c.png"}) == "/c.png"


def test_extract_from_invoke_result():
    res = InvokeResult(ok=True, data={"url": "https://x/v.mp4"})
    assert extract_media_url(res) == "https://x/v.mp4"


def test_extract_empty():
    assert extract_media_url({"foo": "bar"}) == ""
    assert extract_media_url(None) == ""


# ---- content_marketer 消费方兼容（消除静默失败） ----
def test_content_marketer_accepts_url_shape(monkeypatch, tmp_path):
    cm = ContentMarketerAdapter(route_fn=lambda cap, payload: None)
    cm.set_route_fn(lambda cap, payload: InvokeResult(
        ok=True, data={"url": "https://x/media_gen.mp4", "duration": 5.0},
        engine_id="media-gen"))
    # 避免真下载：把落地函数替换成返回固定本地路径
    monkeypatch.setattr(cm, "_localize_video",
                        lambda addr, tid: str(tmp_path / "out.mp4"))
    path, dur = cm._generate_video("scene1\nscene2", "task1")
    assert path.endswith("out.mp4")
    assert dur == 5.0


def test_content_marketer_accepts_local_output_shape(tmp_path):
    cm = ContentMarketerAdapter(route_fn=lambda cap, payload: None)
    local = tmp_path / "local.mp4"
    local.write_bytes(b"fake")
    cm.set_route_fn(lambda cap, payload: InvokeResult(
        ok=True, data={"output": str(local), "duration": 3.0},
        engine_id="video-maker"))
    path, dur = cm._generate_video("s1\ns2", "task2")
    assert path == str(local)
    assert dur == 3.0
