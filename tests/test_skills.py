"""
Unit tests for AOS skills system.
"""



class TestSkillRegistry:
    """Test SkillRegistry class."""

    def test_registry_initialization(self):
        """Test that SkillRegistry initializes empty."""
        from src.skills.base import SkillRegistry

        registry = SkillRegistry()
        assert registry._skills == {}
        assert registry.get_stats()["total"] == 0

    def test_register_skill(self):
        """Test registering a skill."""
        from src.skills.base import SkillRegistry, Skill

        class DummySkill(Skill):
            name = "dummy"
            description = "A dummy skill for testing"

            def _execute_impl(self, context):
                return {"success": True, "result": "dummy done"}

        registry = SkillRegistry()
        registry.register(DummySkill())

        assert "dummy" in registry._skills
        assert registry.get_stats()["total"] == 1

    def test_execute_skill(self):
        """Test executing a registered skill."""
        from src.skills.base import SkillRegistry, Skill

        class AddSkill(Skill):
            name = "add"
            description = "Adds two numbers"

            def _execute_impl(self, context):
                a = context.get("a", 0)
                b = context.get("b", 0)
                return {"success": True, "result": a + b}

        registry = SkillRegistry()
        registry.register(AddSkill())

        result = registry.execute("add", {"a": 5, "b": 3})
        assert result["success"] is True
        assert result["result"] == 8

    def test_execute_nonexistent_skill(self):
        """Test executing a skill that doesn't exist."""
        from src.skills.base import SkillRegistry

        registry = SkillRegistry()
        result = registry.execute("nonexistent", {})
        assert result["success"] is False
        assert "error" in result

    def test_list_skills(self):
        """Test listing all skills."""
        from src.skills.base import SkillRegistry, Skill

        class SkillA(Skill):
            name = "skill_a"
            description = "Skill A"
            category = "test"

        class SkillB(Skill):
            name = "skill_b"
            description = "Skill B"
            category = "test"

        registry = SkillRegistry()
        registry.register(SkillA())
        registry.register(SkillB())

        all_skills = registry.list_all()
        assert len(all_skills) == 2

        test_skills = registry.list_by_category("test")
        assert len(test_skills) == 2

    def test_skill_search(self):
        """Test searching skills by name/description."""
        from src.skills.base import SkillRegistry, Skill

        class SearchableSkill(Skill):
            name = "web_search"
            description = "Search the web for information"
            category = "research"

        registry = SkillRegistry()
        registry.register(SearchableSkill())

        results = registry.search("web")
        assert len(results) == 1
        assert results[0].name == "web_search"

    def test_skill_stats(self):
        """Test getting skill registry statistics."""
        from src.skills.base import SkillRegistry, Skill

        class Cat1Skill(Skill):
            name = "skill1"
            description = "desc1"
            category = "cat1"

        class Cat2Skill(Skill):
            name = "skill2"
            description = "desc2"
            category = "cat2"

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
        from src.skills.base import SkillMeta

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
        from src.skills.base import Skill

        class SimpleSkill(Skill):
            name = "simple"
            description = "Simple test skill"

            def _execute_impl(self, context):
                return {"success": True, "data": context}

        skill = SimpleSkill()
        result = skill.execute({"key": "value"})

        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["data"]["key"] == "value"

    def test_skill_with_validation(self):
        """Test skill with input validation."""
        from src.skills.base import Skill

        class ValidatedSkill(Skill):
            name = "validated"
            description = "Skill with validation"
            required_fields = ["prompt"]

            def _execute_impl(self, context):
                return {"success": True, "prompt": context["prompt"]}

        skill = ValidatedSkill()

        # Valid execution
        result = skill.execute({"prompt": "hello"})
        assert result["success"] is True

        # Missing required field should still work (validation is optional)
        result = skill.execute({})
        assert result.get("prompt") is None  # No error raised by base class
