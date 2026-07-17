"""测试PATH修改确认（V10修复验证）"""
import pytest
from unittest.mock import patch, MagicMock
from core.fabric.adapter import InvokeResult


def test_path_modification_confirmation():
    """测试PATH修改前打印确认消息"""
    import inspect
    from kernel.autopilot import _try_direct_install

    source = inspect.getsource(_try_direct_install)
    assert "即将修改用户PATH" in source or "添加到PATH" in source, "代码中应该在PATH修改前打印确认消息"


def test_path_modification_prints_message():
    """测试PATH修改时会打印消息"""
    from kernel.autopilot import _try_direct_install
    import tempfile
    import zipfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试zip文件
        zip_path = f"{tmpdir}/ffmpeg.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("bin/ffmpeg.exe", "fake exe")

        # 读取zip文件内容
        with open(zip_path, "rb") as f:
            zip_content = f.read()

        # Mock urlopen返回测试zip文件
        mock_response = MagicMock()
        mock_response.read.return_value = zip_content
        mock_response.__enter__ = lambda self: self
        mock_response.__exit__ = lambda self, *args: None

        # Mock subprocess.run返回成功
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = b"ffmpeg version 1.0\n"
        mock_process.stderr = b""

        # Mock print函数
        printed_messages = []
        def mock_print(*args, **kwargs):
            printed_messages.append(" ".join(str(arg) for arg in args))

        with patch("urllib.request.urlopen", return_value=mock_response):
            with patch("subprocess.run", return_value=mock_process):
                with patch("builtins.print", side_effect=mock_print):
                    with patch("kernel.autopilot._add_to_user_path"):
                        with patch("os.walk", return_value=[(f"{tmpdir}/bin", [], ["ffmpeg.exe"])]):
                            result = _try_direct_install("ffmpeg")

        # 验证打印了PATH修改消息
        path_messages = [msg for msg in printed_messages if "PATH" in msg or "path" in msg.lower()]
        assert len(path_messages) > 0, "应该打印PATH修改消息"
        print(f"打印的消息: {printed_messages}")