import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""创业API基础测试。"""
import pytest
from api.startup_api import scan_new_artifacts, snapshot_output_dirs, _file_type


class TestStartupAPI:
    def test_file_type(self):
        """文件类型判断。"""
        assert _file_type("video.mp4") == "video"
        assert _file_type("image.png") == "image"
        assert _file_type("doc.md") == "document"
        assert _file_type("data.csv") == "data"
        assert _file_type("code.py") == "code"
        assert _file_type("unknown.xyz") == "other"

    def test_snapshot_output_dirs(self):
        """快照输出目录。"""
        snap = snapshot_output_dirs()
        assert isinstance(snap, dict)

    def test_scan_new_artifacts_empty(self):
        """空快照扫描。"""
        artifacts = scan_new_artifacts({})
        assert isinstance(artifacts, list)
