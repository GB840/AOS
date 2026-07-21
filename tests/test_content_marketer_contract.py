"""content-marketer 媒体消费契约守护。

固化 P1（统一 media 返回契约）在真实消费方 content-marketer 不退化：
无论 route(media.video) 落到 media-gen（url 形状）还是 video-maker（output 形状），
_generate_video 都该正确取出地址并交给本地化，而非静默返回 ("", 0.0)。

全程 mock 网络下载与 route_fn，零 key、零真实调用。
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from core.fabric.adapter import InvokeResult
from core.fabric.adapters.content_marketer_adapter import ContentMarketerAdapter


def _mk(script: str = "镜头一：日出\n镜头二：奔跑"):
    return script


def test_generate_video_from_media_gen_url_shape(monkeypatch):
    """route 落到 media-gen：返回 {"url": 智谱临时url}，消费方应能取出并本地化。"""
    a = ContentMarketerAdapter(route_fn=lambda cap, payload: InvokeResult(
        ok=True, data={"url": "https://cogvideo.cdn/abc.mp4", "duration": 5.0},
    ))
    # 隔离网络下载：记录 localize 收到的地址，并固定返回本地路径
    seen = {}
    def _fake_localize(addr, tid):
        seen["addr"] = addr
        return "/local/content_x.mp4"
    monkeypatch.setattr(a, "_localize_video", _fake_localize)
    path, dur = a._generate_video(_mk(), "t_url")
    assert seen["addr"] == "https://cogvideo.cdn/abc.mp4"
    assert path == "/local/content_x.mp4"
    assert dur == 5.0


def test_generate_video_from_video_maker_output_shape(monkeypatch):
    """route 落到 video-maker：返回 {"output": 本地路径}，消费方应能原样取到。"""
    a = ContentMarketerAdapter(route_fn=lambda cap, payload: InvokeResult(
        ok=True, data={"output": "/aos/_video_output/aos_video_t_out.mp4", "duration": 8.0},
    ))
    monkeypatch.setattr(a, "_localize_video", lambda addr, tid: addr)
    path, dur = a._generate_video(_mk(), "t_out")
    assert path == "/aos/_video_output/aos_video_t_out.mp4"
    assert dur == 8.0


def test_generate_video_route_failure_graceful():
    """route 失败（返回 None / ok=False）时优雅降级为 ("", 0.0)，不抛。"""
    a = ContentMarketerAdapter(route_fn=lambda cap, payload: None)
    assert a._generate_video(_mk(), "t_fail1") == ("", 0.0)

    a2 = ContentMarketerAdapter(route_fn=lambda cap, payload: InvokeResult(ok=False, error="boom"))
    assert a2._generate_video(_mk(), "t_fail2") == ("", 0.0)


def test_generate_video_empty_script():
    """脚本为空（无分镜）时直接返回空，不触发 route。"""
    a = ContentMarketerAdapter(route_fn=lambda cap, payload: (_ for _ in ()).throw(
        AssertionError("route 不该被调用")))
    assert a._generate_video("", "t_empty") == ("", 0.0)
