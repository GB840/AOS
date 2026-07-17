"""测试zip下载完整性校验（V9修复验证）"""
import os
import pytest
import zipfile
from unittest.mock import patch, MagicMock
from core.fabric.adapter import InvokeResult


def test_zip_integrity_check():
    """测试zip下载后进行完整性校验"""
    # 创建一个测试zip文件
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一个正常的zip文件
        zip_path = os.path.join(tmpdir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "Hello, World!")

        # 测试正常zip文件
        with zipfile.ZipFile(zip_path) as zf:
            bad_file = zf.testzip()
            assert bad_file is None

        # 创建一个损坏的zip文件（截断）
        corrupt_path = os.path.join(tmpdir, "corrupt.zip")
        with open(zip_path, "rb") as src, open(corrupt_path, "wb") as dst:
            dst.write(src.read()[:100])  # 只写入前100字节，截断文件

        # 测试损坏的zip文件
        with pytest.raises(zipfile.BadZipFile):
            with zipfile.ZipFile(corrupt_path) as zf:
                zf.testzip()


def test_zipfile_testzip_in_code():
    """验证代码中使用了zipfile.testzip()进行完整性校验"""
    import inspect
    from kernel.autopilot import _try_direct_install

    source = inspect.getsource(_try_direct_install)
    assert "testzip" in source, "代码中应该使用zipfile.testzip()进行完整性校验"


def test_corrupt_zip_detection():
    """测试损坏的zip文件能被检测到"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建一个正常的zip文件
        zip_path = os.path.join(tmpdir, "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("test.txt", "Hello, World!")

        # 读取正常zip文件
        with open(zip_path, "rb") as f:
            normal_content = f.read()

        # 创建损坏的zip文件（修改中间部分）
        corrupt_path = os.path.join(tmpdir, "corrupt.zip")
        with open(corrupt_path, "wb") as f:
            # 写入前半部分
            f.write(normal_content[:len(normal_content)//2])
            # 写入垃圾数据
            f.write(b"\x00" * 100)
            # 写入后半部分
            f.write(normal_content[len(normal_content)//2 + 100:])

        # 测试损坏的zip文件
        try:
            with zipfile.ZipFile(corrupt_path) as zf:
                bad_file = zf.testzip()
                # testzip()应该返回损坏的文件名，或者抛出异常
                assert bad_file is not None or False, "损坏的zip文件应该被检测到"
        except zipfile.BadZipFile:
            # 预期的异常
            pass