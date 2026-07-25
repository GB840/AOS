"""Img2ThreejsAdapter 真实通电测试（media.3d.reconstruct）。

诚实优先：probe/score 用真造 PNG **真跑 vendored 脚本**（纯 stdlib，无需装依赖），
不 mock 脚本执行——验证「脚本层确定性能力」是真的。pipeline 验证诚实指引；
另验诚实失败路径（未知 action / 缺图 / vendored 缺失时 health=False）。
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from core.fabric.adapters import Img2ThreejsAdapter
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability

CAP = Capability.MEDIA_3D_RECONSTRUCT
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _write_png(path: Path, w: int, h: int, pixel_fn) -> None:
    """用 stdlib struct/zlib 写一张 RGB PNG（仿上游 test helper）。"""
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(pixel_fn(x, y))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    path.write_bytes(_PNG_SIG + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


def _block(x0, y0, x1, y1, fg=(200, 40, 40), bg=(255, 255, 255)):
    return lambda x, y: fg if (x0 <= x < x1 and y0 <= y < y1) else bg


@pytest.fixture
def adapter():
    return Img2ThreejsAdapter()


def test_basic_contract(adapter):
    assert adapter.engine_id == "img2threejs"
    assert Capability.MEDIA_3D_RECONSTRUCT in adapter.advertise_capabilities()
    assert adapter.tier() == "high"


def test_health_true_when_vendored_present(adapter):
    # vendored 于 third_party/img2threejs，脚本齐全 → 可用
    assert adapter.health() is True
    hd = adapter.health_detail()
    assert hd["available"] is True
    assert "img2threejs" in hd["root"]


def test_health_false_when_missing(tmp_path):
    a = Img2ThreejsAdapter(root=tmp_path / "nope")
    assert a.health() is False
    r = a.invoke(InvokeRequest(capability=CAP, payload={"action": "probe",
                                                        "image": "x"}))
    assert r.ok is False
    assert "不可用" in r.error


def test_pipeline_returns_honest_guidance(adapter):
    r = adapter.invoke(InvokeRequest(capability=CAP,
                                     payload={"action": "pipeline", "name": "earbud"}))
    assert r.ok is True
    d = r.data
    assert set(d["stages"]) == {"stage1_intake", "stage2_spec",
                                "stage3_build", "stage4_review"}
    assert d["driver"] == "agent"
    # 诚实纪律：不谎报一次出成品
    assert "不谎报" in d["honest_note"]
    assert Path(d["skill_doc"]).name == "SKILL.md"


def test_probe_runs_real_script(adapter, tmp_path):
    img = tmp_path / "ref.png"
    _write_png(img, 120, 120, _block(30, 30, 90, 90))
    r = adapter.invoke(InvokeRequest(capability=CAP,
                                     payload={"action": "probe", "image": str(img)}))
    assert r.ok is True, r.error
    res = r.data["result"]
    assert isinstance(res, dict)
    assert res["type"] == "png"
    assert res["width"] == 120 and res["height"] == 120


def test_score_runs_real_divine_eye(adapter, tmp_path):
    ref = tmp_path / "ref.png"
    ren = tmp_path / "ren.png"
    _write_png(ref, 200, 200, _block(50, 50, 150, 150))
    _write_png(ren, 200, 200, _block(52, 52, 148, 148))  # 近似 → 高分
    r = adapter.invoke(InvokeRequest(capability=CAP, payload={
        "action": "score", "reference": str(ref), "render": str(ren)}))
    assert r.ok is True, r.error
    verdict = r.data["verdict"]
    assert isinstance(verdict, dict)
    # divine_eye 输出应含某种总体结论（verdict / score / 类似字段）
    assert verdict  # 非空 JSON


def test_score_requires_both_images(adapter, tmp_path):
    ref = tmp_path / "ref.png"
    _write_png(ref, 60, 60, _block(10, 10, 50, 50))
    r = adapter.invoke(InvokeRequest(capability=CAP, payload={
        "action": "score", "reference": str(ref)}))
    assert r.ok is False
    assert "render" in r.error


def test_unknown_action_rejected(adapter):
    r = adapter.invoke(InvokeRequest(capability=CAP, payload={"action": "boom"}))
    assert r.ok is False
    assert "boom" in r.error


def test_probe_missing_image(adapter):
    r = adapter.invoke(InvokeRequest(capability=CAP, payload={
        "action": "probe", "image": "/no/such/file.png"}))
    assert r.ok is False
    assert "不存在" in r.error
