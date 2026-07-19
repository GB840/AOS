"""内容飞轮技能测试 — 覆盖模拟执行、反思提炼、教训持久化、trace 完整性。"""
import json
import sys
import os
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skills.content_flywheel_skill import (
    ContentFlywheelSkill,
    REFLECTION_RULES,
)


@pytest.fixture
def skill(tmp_path):
    """创建使用临时目录的 skill 实例。"""
    os.environ["AOS_FLYWHEEL_LESSONS_DIR"] = str(tmp_path / "lessons")
    # 重新 import 以刷新模块级路径
    import importlib
    import skills.content_flywheel_skill as mod
    importlib.reload(mod)
    s = mod.ContentFlywheelSkill()
    s._lessons_path = tmp_path / "lessons" / "flywheel_lessons.jsonl"
    return s


class TestExecute:
    """execute() 主入口测试。"""

    def test_missing_topic(self, skill):
        result = skill.execute({})
        assert result["success"] is False
        assert "topic" in result["error"]

    def test_empty_topic(self, skill):
        result = skill.execute({"topic": "   "})
        assert result["success"] is False

    def test_simulated_mode(self, skill):
        result = skill.execute({"topic": "AI 智能体", "max_cycles": 2})
        assert result["success"] is True
        assert result["mode"] == "simulated"
        assert result["total_cycles"] == 2
        assert result["completed_cycles"] == 2
        assert len(result["cycles"]) == 2

    def test_max_cycles_capped(self, skill):
        result = skill.execute({"topic": "test", "max_cycles": 100})
        assert result["total_cycles"] <= 20

    def test_platforms_config(self, skill):
        result = skill.execute({
            "topic": "test",
            "max_cycles": 1,
            "platforms": ["douyin", "bilibili", "xiaohongshu"],
        })
        forge = result["cycles"][0]["stages"]["cast"]
        assert forge["package_count"] == 3

    def test_trace_present(self, skill):
        result = skill.execute({"topic": "trace test", "max_cycles": 1})
        trace = result.get("trace")
        assert trace is not None
        assert trace["skill"] == "content-flywheel"
        assert trace["topic"] == "trace test"
        assert "ts" in trace
        assert "elapsed_seconds" in trace

    def test_lessons_injected_flag(self, skill):
        # 先写入一条教训
        skill.save_lesson("测试教训：开头不要太长", context="topic=test")
        result = skill.execute({"topic": "test", "max_cycles": 1, "inject_lessons": True})
        assert result["lessons_injected"] >= 1

    def test_lessons_not_injected(self, skill):
        skill.save_lesson("测试教训", context="")
        result = skill.execute({"topic": "test", "max_cycles": 1, "inject_lessons": False})
        assert result["lessons_injected"] == 0


class TestReflection:
    """反思提炼测试。"""

    def test_stage_failure_lesson(self, skill):
        result = {
            "cycles": [{
                "cycle_num": 1,
                "status": "partial",
                "stages": {
                    "forge": {"ok": True},
                    "cast": {"ok": False, "error": "platform API timeout"},
                    "echo": {"ok": True, "total_count": 10},
                    "refine": {"ok": True},
                },
            }],
        }
        lessons = skill._reflect(result, "test topic")
        assert any("cast" in l for l in lessons)

    def test_no_feedback_lesson(self, skill):
        result = {
            "cycles": [{
                "cycle_num": 1,
                "status": "completed",
                "stages": {
                    "forge": {"ok": True},
                    "cast": {"ok": True},
                    "echo": {"ok": True, "total_count": 0},
                    "refine": {"ok": True},
                },
            }],
        }
        lessons = skill._reflect(result, "test")
        assert any("Echo" in l or "反馈" in l for l in lessons)

    def test_topic_drift_lesson(self, skill):
        result = {
            "final_topic": "完全不同的主题",
            "cycles": [{"cycle_num": 1, "status": "completed", "stages": {
                "forge": {"ok": True}, "cast": {"ok": True},
                "echo": {"ok": True, "total_count": 20}, "refine": {"ok": True},
            }}],
        }
        lessons = skill._reflect(result, "原始主题")
        assert any("漂移" in l for l in lessons)

    def test_repeated_failure_lesson(self, skill):
        result = {
            "cycles": [
                {"cycle_num": 1, "status": "partial", "stages": {
                    "forge": {"ok": False, "error": "OOM"}, "cast": {"ok": True},
                    "echo": {"ok": True, "total_count": 5}, "refine": {"ok": True},
                }},
                {"cycle_num": 2, "status": "partial", "stages": {
                    "forge": {"ok": False, "error": "OOM again"}, "cast": {"ok": True},
                    "echo": {"ok": True, "total_count": 5}, "refine": {"ok": True},
                }},
            ],
        }
        lessons = skill._reflect(result, "test")
        assert any("连续" in l for l in lessons)

    def test_no_lessons_on_success(self, skill):
        result = {
            "cycles": [{
                "cycle_num": 1,
                "status": "completed",
                "stages": {
                    "forge": {"ok": True},
                    "cast": {"ok": True},
                    "echo": {"ok": True, "total_count": 50},
                    "refine": {"ok": True},
                },
            }],
        }
        lessons = skill._reflect(result, "test")
        # 全成功 + 高互动 → 无教训
        assert len(lessons) == 0

    def test_dedup_lessons(self, skill):
        # 两轮相同失败 → 只出一条 stage_failed + 一条 repeated_failure
        result = {
            "cycles": [
                {"cycle_num": i, "status": "partial", "stages": {
                    "forge": {"ok": False, "error": "same error"},
                    "cast": {"ok": True},
                    "echo": {"ok": True, "total_count": 10},
                    "refine": {"ok": True},
                }}
                for i in range(1, 3)
            ],
        }
        lessons = skill._reflect(result, "test")
        # 不应有完全重复的条目
        assert len(lessons) == len(set(lessons))


class TestLessons:
    """教训持久化测试。"""

    def test_save_and_load(self, skill):
        skill.save_lesson("第一条教训", context="topic=A")
        skill.save_lesson("第二条教训", context="topic=B")
        lessons = skill._load_lessons()
        assert len(lessons) == 2
        assert lessons[0]["lesson"] == "第一条教训"
        assert lessons[1]["lesson"] == "第二条教训"

    def test_bounded_rotation(self, skill):
        for i in range(60):
            skill.save_lesson(f"教训 {i}", context="")
        lessons = skill._load_lessons()
        assert len(lessons) <= 50

    def test_empty_lesson_skipped(self, skill):
        skill.save_lesson("", context="")
        skill.save_lesson("ab", context="")  # < 5 chars
        lessons = skill._load_lessons()
        assert len(lessons) == 0

    def test_lesson_length_capped(self, skill):
        long_lesson = "x" * 1000
        skill.save_lesson(long_lesson, context="")
        lessons = skill._load_lessons()
        assert len(lessons[0]["lesson"]) <= 500


class TestReport:
    """报告格式化测试。"""

    def test_format_report_basic(self, skill):
        result = skill.execute({"topic": "报告测试", "max_cycles": 2})
        report = skill.format_report(result)
        assert "内容飞轮执行报告" in report
        assert "报告测试" in report
        assert "模拟演示" in report

    def test_format_report_contains_stages(self, skill):
        result = skill.execute({"topic": "stages", "max_cycles": 1})
        report = skill.format_report(result)
        assert "forge" in report
        assert "cast" in report
        assert "echo" in report
        assert "refine" in report


class TestReflectionRules:
    """反思规则定义完整性。"""

    def test_rules_have_required_fields(self):
        for rule in REFLECTION_RULES:
            assert rule.rule_id
            assert rule.condition
            assert rule.lesson_template
            assert rule.severity in ("high", "medium", "low")

    def test_rule_ids_unique(self):
        ids = [r.rule_id for r in REFLECTION_RULES]
        assert len(ids) == len(set(ids))
