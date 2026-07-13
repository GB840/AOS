"""
Unit tests for AOS skills system (src/skills/base.py).

修复记录 (2026-07-11):
- 属性名小写→大写 (name→NAME, description→DESCRIPTION, ...)
- _execute_impl→execute (基类无模板方法, 必须直接覆盖 execute())
- 添加 _reset_singleton fixture 解决 SkillRegistry 单例状态泄漏
- search() 返回 dict list, 修正断言访问方式
"""

import importlib.util
import pathlib

import pytest

# 直接加载 base.py, 绕过 skills/__init__.py 的 40+ 重型模块级联导入.
# 这样测试只依赖 base.py 本身 (dataclasses + logging), 毫秒级完成.
_base_path = pathlib.Path(__file__).resolve().parent.parent / "src" / "skills" / "base.py"
_spec = importlib.util.spec_from_file_location("_skills_base", _base_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
Skill = _mod.Skill
SkillRegistry = _mod.SkillRegistry
SkillMeta = _mod.SkillMeta


@pytest.fixture(autouse=True)
def _reset_skill_registry():
    """每个测试前重置 SkillRegistry 单例, 确保测试隔离."""
    yield
    # teardown: 清空单例内部状态
    SkillRegistry._instance = None
    inst = SkillRegistry()
    inst._skills.clear()
    inst._initialized = False


class TestSkillRegistry:
    """Test SkillRegistry class."""

    def test_registry_initialization(self):
        """Test that SkillRegistry initializes empty."""
        registry = SkillRegistry()
        assert registry._skills == {}
        assert registry.get_stats()["total"] == 0

    def test_register_skill(self):
        """Test registering a skill."""

        class DummySkill(Skill):
            NAME = "dummy"
            DESCRIPTION = "A dummy skill for testing"

            def execute(self, context):
                return {"success": True, "result": "dummy done"}

        registry = SkillRegistry()
        registry.register(DummySkill())

        assert "dummy" in registry._skills
        assert registry.get_stats()["total"] == 1

    def test_execute_skill(self):
        """Test executing a registered skill."""

        class AddSkill(Skill):
            NAME = "add"
            DESCRIPTION = "Adds two numbers"

            def execute(self, context):
                a = context.get("a", 0)
                b = context.get("b", 0)
                return a + b

        registry = SkillRegistry()
        registry.register(AddSkill())

        result = registry.execute("add", {"a": 5, "b": 3})
        assert result["success"] is True
        assert result["data"] == 8

    def test_execute_nonexistent_skill(self):
        """Test executing a skill that doesn't exist."""
        registry = SkillRegistry()
        result = registry.execute("nonexistent", {})
        assert result["success"] is False
        assert "error" in result

    def test_list_skills(self):
        """Test listing all skills."""

        class SkillA(Skill):
            NAME = "skill_a"
            DESCRIPTION = "Skill A"
            CATEGORY = "test"

        class SkillB(Skill):
            NAME = "skill_b"
            DESCRIPTION = "Skill B"
            CATEGORY = "test"

        registry = SkillRegistry()
        registry.register(SkillA())
        registry.register(SkillB())

        all_skills = registry.list_all()
        assert len(all_skills) == 2

        test_skills = registry.list_by_category("test")
        assert len(test_skills) == 2

    def test_skill_search(self):
        """Test searching skills by name/description."""

        class SearchableSkill(Skill):
            NAME = "web_search"
            DESCRIPTION = "Search the web for information"
            CATEGORY = "research"

        registry = SkillRegistry()
        registry.register(SearchableSkill())

        results = registry.search("web")
        assert len(results) == 1
        assert results[0]["name"] == "web_search"

    def test_skill_stats(self):
        """Test getting skill registry statistics."""

        class Cat1Skill(Skill):
            NAME = "skill1"
            DESCRIPTION = "desc1"
            CATEGORY = "cat1"

        class Cat2Skill(Skill):
            NAME = "skill2"
            DESCRIPTION = "desc2"
            CATEGORY = "cat2"

        registry = SkillRegistry()
        registry.register(Cat1Skill())
        registry.register(Cat2Skill())

        stats = registry.get_stats()
        assert stats["total"] == 2
        assert "cat1" in stats["categories"]
        assert "cat2" in stats["categories"]


class TestSkillBase:
    """Test the base Skill class."""

    def test_skill_meta_creation(self):
        """Test SkillMeta dataclass."""
        meta = SkillMeta(
            name="test_skill",
            description="A test skill",
            category="testing",
            version="1.0.0",
            tags=["test", "demo"],
        )
        assert meta.name == "test_skill"
        assert meta.category == "testing"
        assert "test" in meta.tags

    def test_skill_execute_returns_dict(self):
        """Test that skill execute returns a dict result."""

        class SimpleSkill(Skill):
            NAME = "simple"
            DESCRIPTION = "Simple test skill"

            def execute(self, context):
                return {"success": True, "data": context}

        skill = SimpleSkill()
        result = skill.execute({"key": "value"})

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["data"]["key"] == "value"

    def test_skill_with_validation(self):
        """Test skill with input validation."""

        class ValidatedSkill(Skill):
            NAME = "validated"
            DESCRIPTION = "Skill with validation"

            def execute(self, context):
                return {"success": True, "prompt": context.get("prompt")}

        skill = ValidatedSkill()

        # Valid execution
        result = skill.execute({"prompt": "hello"})
        assert result["success"] is True
        assert result["prompt"] == "hello"

        # Missing field: get() returns None, no error raised
        result = skill.execute({})
        assert result.get("prompt") is None

    def test_skill_name_property(self):
        """Test that name property reads from meta (set via NAME)."""

        class NamedSkill(Skill):
            NAME = "my_named_skill"
            DESCRIPTION = "test"

        skill = NamedSkill()
        assert skill.name == "my_named_skill"

    def test_skill_to_dict(self):
        """Test to_dict returns correct structure."""

        class DictSkill(Skill):
            NAME = "dict_skill"
            DESCRIPTION = "dict test"
            CATEGORY = "testing"
            TAGS = ["a", "b"]

        d = DictSkill().to_dict()
        assert d["name"] == "dict_skill"
        assert d["category"] == "testing"
        assert "a" in d["tags"]

    def test_skill_to_skill_md(self):
        """Test SKILL.md export."""

        class MdSkill(Skill):
            NAME = "md_skill"
            DESCRIPTION = "markdown test"

        md = MdSkill().to_skill_md()
        assert "md_skill" in md
        assert "markdown test" in md
        assert md.startswith("---")

    def test_skill_execute_not_implemented(self):
        """Test that base execute() raises NotImplementedError."""

        class BareSkill(Skill):
            NAME = "bare"
            DESCRIPTION = "no execute"

        with pytest.raises(NotImplementedError):
            BareSkill().execute({})

    def test_registry_unregister(self):
        """Test unregistering a skill."""

        class UnregSkill(Skill):
            NAME = "unreg"
            DESCRIPTION = "to be unregistered"

            def execute(self, ctx):
                return {}

        registry = SkillRegistry()
        registry.register(UnregSkill())
        assert registry.has("unreg")

        assert registry.unregister("unreg") is True
        assert not registry.has("unreg")
        assert registry.unregister("nonexistent") is False

    def test_registry_export_all(self, tmp_path):
        """Test exporting all skills to SKILL.md files."""

        class ExpSkill1(Skill):
            NAME = "exp1"
            DESCRIPTION = "export 1"

        class ExpSkill2(Skill):
            NAME = "exp2"
            DESCRIPTION = "export 2"

        registry = SkillRegistry()
        registry.register(ExpSkill1())
        registry.register(ExpSkill2())

        count = registry.export_all_skill_md(tmp_path)
        assert count == 2
        assert (tmp_path / "exp1.md").exists()
        assert (tmp_path / "exp2.md").exists()
