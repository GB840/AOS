"""scroll_world_demo 构建器离线单元测试（零网络、零 key、零内核依赖）。

覆盖：场景派生、配色匹配、render_html 结构（full/grid）、palette 注入、
未替换占位符、单场景失败隔离。真实出图/视频路径由人工真机验证覆盖
（用户主机已实跑 4 幕图+视频全绿，295s）。
"""
import os
import re
import shutil
import sys

import pytest

_EXAMPLES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
)
if _EXAMPLES not in sys.path:
    sys.path.insert(0, _EXAMPLES)

import scroll_world_demo as m


def _rm(path):
    shutil.rmtree(path, ignore_errors=True)


def test_build_scenes_derives_n():
    scenes = m.build_scenes("测试主题", 5)
    assert len(scenes) == 5
    assert all(s["title"] and s["image_prompt"] and s["video_prompt"] for s in scenes)
    assert all(s["video"] is False for s in scenes)


def test_pick_palette_keyword():
    assert m.pick_palette("赛博朋克城市")["label"] == "赛博朋克"
    assert m.pick_palette("国风山水")["label"] == "国风"
    assert m.pick_palette("未来都市")["label"] == "未来都市"
    assert m.pick_palette("自然奇观")["label"] == "自然"


def test_pick_palette_default_future():
    assert m.pick_palette("完全不相关主题")["label"] == "未来都市"


def test_pick_palette_override():
    # --palette 强制覆盖
    assert m.pick_palette("赛博", override="guofeng")["label"] == "国风"
    # 未知 override 回退到关键词/默认
    assert m.pick_palette("未来都市", override="nope")["label"] == "未来都市"


def test_render_html_full_no_video():
    scenes = m.build_scenes("主题", 3)
    rendered = [
        {"title": s["title"], "caption": s["caption"],
         "image": f"assets/scene_{i+1}.png", "videos": [], "video": None}
        for i, s in enumerate(scenes)
    ]
    out = "out/_t_full_ut"
    os.makedirs(out, exist_ok=True)
    try:
        p = m.render_html(rendered, out, m.pick_palette("主题"), dry_run=True)
        html = open(p, encoding="utf-8").read()
        assert html.count('class="scene"') == 3
        assert html.count('class="dot"') == 3
        assert "calc(3 * 100vh)" in html
        assert html.count('<img class="bg"') == 3
        assert "--accent:" in html
    finally:
        _rm(out)


def test_render_html_grid_video_structure():
    rendered = [
        {"title": f"幕{i+1}", "caption": "x", "image": f"assets/scene_{i+1}.png",
         "videos": [f"assets/scene_{i+1}_v{j+1}.mp4" for j in range(4)],
         "video": "assets/scene_1_v1.mp4"}
        for i in range(2)
    ]
    out = "out/_t_grid_ut"
    os.makedirs(out, exist_ok=True)
    try:
        p = m.render_html(rendered, out, m.pick_palette("主题"), dry_run=False)
        html = open(p, encoding="utf-8").read()
        assert html.count('class="media grid"') == 2
        assert html.count("data-scrub") == 8          # 2 场景 × 4 路视频
        assert html.count("<video") == 8
        assert html.count('poster="assets/scene_1.png"') == 4  # 复用当幕图作封面
    finally:
        _rm(out)


def test_render_html_palette_injection():
    rendered = [{"title": "T", "caption": "c", "image": "assets/s1.png",
                 "videos": [], "video": None}]
    out = "out/_t_pal_ut"
    os.makedirs(out, exist_ok=True)
    try:
        p = m.render_html(rendered, out, m.PALETTES["cyber"], dry_run=True)
        html = open(p, encoding="utf-8").read()
        assert "--accent: #00f0ff" in html
        assert "--grad-a: #00f0ff" in html
    finally:
        _rm(out)


def test_failure_isolation_all_fail():
    """所有生成失败时仍产出占位图续跑、页面照常构建、不抛。"""
    class FakeRes:
        def __init__(self, ok, data=None, error=None):
            self.ok = ok
            self.data = data
            self.error = error

    class FakeHub:
        def invoke_engine(self, engine, cap, payload):
            return FakeRes(False, error="模拟生成失败")

    scenes = m.build_scenes("主题", 3)
    out = "out/_t_fail_ut"
    os.makedirs(out, exist_ok=True)
    try:
        rendered = m.generate_assets(
            FakeHub(), scenes, out, dry_run=False, with_video=True, layout="split"
        )
        assert len(rendered) == 3
        assert all(r["image"] for r in rendered)
        assert all(r["video"] is None for r in rendered)
        p = m.render_html(rendered, out, m.pick_palette("主题"), dry_run=False)
        html = open(p, encoding="utf-8").read()
        assert html.count('class="scene"') == 3
    finally:
        _rm(out)


def test_dryrun_no_unreplaced_tokens():
    scenes = m.build_scenes("主题", 2)
    out = "out/_t_tokens_ut"
    os.makedirs(out, exist_ok=True)
    try:
        rendered = m.generate_assets(
            None, scenes, out, dry_run=True, with_video=True, layout="grid"
        )
        p = m.render_html(rendered, out, m.pick_palette("主题"), dry_run=True)
        html = open(p, encoding="utf-8").read()
        assert not re.search(r"__[A-Z_]+__", html), "存在未替换占位符"
    finally:
        _rm(out)
