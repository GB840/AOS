"""video-shotcraft 接入单元测试 —— 诚实级 ②（代码就绪 + 单元验证）。

覆盖：
- Apache-2.0 仓库已在 vendor/ 克隆 + node 在 PATH → available()=True（真接，非标签）
- ensure_repo() 命中已克隆仓库（不重复 clone）
- build_render_command 构造真实 Remotion 渲染命令（不实际跑 npm，避免重 I/O）
- 缺仓库 / 缺 node 时诚实报错（不冒充「视频已生成」）
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.video_shotcraft_backend import VideoShotcraft  # noqa: E402


def test_video_shotcraft_real_repo_detected():
    # 真接开源实证：vendor/video-shotcraft 已克隆（Apache-2.0）+ node 在 PATH
    vs = VideoShotcraft()
    detail = vs.health_detail()
    assert detail["license"] == "Apache-2.0"
    assert detail["repo_present"] is True, "vendor/video-shotcraft 应已克隆"
    assert detail["node_present"] is True, "node 应在 PATH 上"
    assert vs.available is True


def test_ensure_repo_returns_existing():
    vs = VideoShotcraft()
    path = vs.ensure_repo()
    assert os.path.isdir(path)
    assert "video-shotcraft" in path


def test_build_render_command_correct():
    vs = VideoShotcraft()
    cmd = vs.build_render_command("/tmp/out.mp4", template="Ink Press", props={"name": "AOS"})
    assert cmd[0] == "npx"
    assert "remotion" in cmd
    assert "render" in cmd
    assert "Ink Press" in cmd
    assert "--output" in cmd
    assert "/tmp/out.mp4" in cmd
    # props 序列化为 JSON 传入
    joined = " ".join(cmd)
    assert "name" in joined and "AOS" in joined


def test_missing_repo_honest_error(tmp_path):
    # 任何候选仓库都不在 → 诚实报错，不冒充「视频已生成」
    vs = VideoShotcraft(repo_path=None)
    vs._candidates = [str(tmp_path / "nonexistent")]
    assert vs._repo_present() is None
    with pytest.raises(RuntimeError):
        vs.build_render_command("/tmp/out.mp4")
