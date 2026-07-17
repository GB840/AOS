"""Skill 注册表冒烟测试——验证 manifest 可读、discover 可查、FabricHub 可调。"""
import json
from pathlib import Path

from kernel.skill_registry import SkillRegistry, get_skill_registry


def test_skill_registry_loads_manifest():
    reg = SkillRegistry()
    assert reg._loaded, "注册表未加载"
    assert len(reg._skills) >= 25, f"技能数偏少：{len(reg._skills)}"
    assert len(reg._by_capability) >= 5, f"能力数偏少：{len(reg._by_capability)}"


def test_skill_registry_discovers_web_search():
    reg = SkillRegistry()
    skills = reg.discover("web.search")
    assert skills, "未发现 web.search 能力对应的技能"
    names = [s["name"] for s in skills]
    assert "DuckDuckGo Search" in names


def test_skill_registry_discovers_media_image():
    reg = SkillRegistry()
    skills = reg.discover("media.image")
    assert any(s["name"] == "ComfyUI" for s in skills)


def test_skill_registry_nonexistent_capability_returns_empty():
    reg = SkillRegistry()
    assert reg.discover("this.does.not.exist") == []


def test_skill_registry_get_skill_by_id():
    reg = SkillRegistry()
    s = reg.get_skill("comfyui")
    assert s is not None
    assert s["name"] == "ComfyUI"
    assert "media.image" in s["capabilities"]


def test_skill_registry_list_all_sorted():
    reg = SkillRegistry()
    all_skills = reg.list_all()
    assert len(all_skills) >= 25
    ids = [s["id"] for s in all_skills]
    assert ids == sorted(ids), "list_all 未按 id 排序"


def test_skill_registry_summary():
    reg = SkillRegistry()
    s = reg.summary()
    assert s["total_skills"] >= 25
    assert s["loaded"] is True
    assert "meta" in s["categories"]


def test_skill_registry_singleton():
    r1 = get_skill_registry()
    r2 = get_skill_registry()
    assert r1 is r2, "get_skill_registry 未返回单例"


def test_skill_registry_missing_manifest_zero_impact():
    reg = SkillRegistry(manifest_path="/nonexistent/manifest.json")
    assert len(reg._skills) == 0
    assert reg.discover("web.search") == []
    assert reg.summary()["total_skills"] == 0
