"""comfyui 适配器资产落地守护。

ComfyUI 输出在它私有目录（相对 cwd 且有歧义），web/下游不可稳定引用。
验证 ComfyUIAdapter.invoke 把 output_path 拷贝到 AOS 拥有的 out/comfyui/
并返回绝对路径（同时填 url），且源缺失时不静默丢资产。
"""
import os
import sys
import types
from unittest import mock

sys.path.insert(0, "src")

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from kernel.plugins.comfyui_adapter import ComfyUIAdapter


def _patch_comfyui(execute_return, monkeypatch, tmp_path):
    """隔离 skills.comfyui 重型依赖，注入假的 ComfyUISkill.execute。"""
    class FakeSkill:
        def execute(self, ctx):
            return execute_return
    fake_mod = types.SimpleNamespace(ComfyUISkill=FakeSkill, ComfyUIDirector=object)
    monkeypatch.setitem(sys.modules, "skills.comfyui", fake_mod)
    monkeypatch.chdir(tmp_path)  # 让 out/comfyui 落在 tmp，不污染仓库


def test_invoke_localizes_output_to_aos_dir(monkeypatch, tmp_path):
    src = tmp_path / "comfyui_private" / "cat.png"
    src.parent.mkdir()
    src.write_bytes(b"fake-png")
    _patch_comfyui(
        {"success": True, "result": {"output_path": str(src)}, "action_name": "文生图"},
        monkeypatch, tmp_path,
    )
    a = ComfyUIAdapter()
    res = a.invoke(InvokeRequest(capability=Capability.MEDIA_IMAGE, payload={"prompt": "猫"}))
    assert res.ok
    out = res.data["output_path"]
    # 落在 AOS 拥有的 out/comfyui/ 且为绝对路径
    assert os.path.isabs(out)
    assert "out/comfyui" in out.replace("\\", "/")
    assert os.path.exists(out)
    # url 与 output_path 一致（归一化投影，供网页引用）
    assert res.data["url"] == out


def test_localize_missing_source_returns_abspath(monkeypatch, tmp_path):
    """源文件不存在时不拷贝、不崩，退回 abspath。"""
    _patch_comfyui(
        {"success": True, "result": {"output_path": "/no/such/file.png"}},
        monkeypatch, tmp_path,
    )
    a = ComfyUIAdapter()
    res = a.invoke(InvokeRequest(capability=Capability.MEDIA_IMAGE, payload={"prompt": "x"}))
    assert res.ok
    assert res.data["output_path"] == os.path.abspath("/no/such/file.png")
    assert res.data["url"] == res.data["output_path"]
