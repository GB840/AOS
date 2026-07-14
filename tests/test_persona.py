"""人设配置化测试：默认/设置/重载/隔离/重置/未知字段保留。"""
import os

import pytest

import core.fabric.persona as PZ


@pytest.fixture
def iso(tmp_path, monkeypatch):
    monkeypatch.setenv("AOS_COMPANION_DIR", str(tmp_path))
    PZ._CACHE.clear()
    yield tmp_path


def test_default_persona(iso):
    p = PZ.load_persona("default")
    assert p["name"] == "小元"
    assert "mood_emojis" in p
    assert p["avatar"] == "🌟"


def test_set_and_reload(iso):
    PZ.save_persona("alice", {"name": "小爱", "tts_voice": "zh-CN-XiaoxiaoNeural"})
    assert (iso / "personas" / "alice.yaml").exists()
    PZ._CACHE.clear()
    assert PZ.load_persona("alice")["name"] == "小爱"
    assert PZ.load_persona("alice")["tts_voice"] == "zh-CN-XiaoxiaoNeural"


def test_per_user_isolation(iso):
    PZ.save_persona("a", {"name": "A"})
    PZ.save_persona("b", {"name": "B"})
    PZ._CACHE.clear()
    assert PZ.load_persona("a")["name"] == "A"
    assert PZ.load_persona("b")["name"] == "B"


def test_reset(iso):
    PZ.save_persona("a", {"name": "X"})
    PZ.reset_persona("a")
    PZ._CACHE.clear()
    assert PZ.load_persona("a")["name"] == "小元"


def test_merge_keeps_unknown_fields(iso):
    merged = PZ.save_persona("a", {"custom_field": "hi"})
    assert merged.get("custom_field") == "hi"
    assert merged["name"] == "小元"  # 默认字段保留


def test_empty_value_not_overwrite(iso):
    PZ.save_persona("a", {"name": "A"})
    # 空值不覆盖已有值
    merged = PZ.save_persona("a", {"name": ""})
    assert merged["name"] == "A"
