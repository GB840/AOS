"""内容飞轮引擎反思闭环测试 — 直接测 kernel.plugins.content_flywheel 的 lesson 能力。

不测 Skill 包装层（那只是委托），测引擎本身的：
- _save_lesson / _load_lessons 持久化
- _reflect_and_persist 提炼逻辑
- _stage_forge 教训注入
- 有界轮转 + 线程安全
"""
import json
import os
import sys
import threading
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture(autouse=True)
def isolate_lessons(tmp_path, monkeypatch):
    """每轮测试隔离教训文件，不污染真实数据。"""
    lessons_file = tmp_path / "flywheel_lessons.jsonl"
    state_dir = str(tmp_path / "flywheel_state")
    os.makedirs(state_dir, exist_ok=True)
    monkeypatch.setenv("AOS_FLYWHEEL_STATE_DIR", state_dir)
    import kernel.plugins.content_flywheel as mod
    monkeypatch.setattr(mod, "_LESSONS_PATH", str(lessons_file))
    monkeypatch.setattr(mod, "_STATE_DIR", state_dir)
    return mod


@pytest.fixture
def flywheel(isolate_lessons):
    """构建无 route_fn 的飞轮实例（测试反思逻辑不需要真实路由）。"""
    return isolate_lessons.ContentFlywheel(topic="AI 智能体", route_fn=None)


class TestLessonPersistence:
    """_save_lesson / _load_lessons 持久化。"""

    def test_save_and_load(self, isolate_lessons):
        mod = isolate_lessons
        mod._save_lesson("AI 智能体", 1, "forge", "forge 阶段超时，应降低视频时长")
        mod._save_lesson("AI 智能体", 2, "echo", "Echo 采集 0 条，关键词不匹配")
        lessons = mod._load_lessons("AI 智能体")
        assert len(lessons) == 2

    def test_topic_relevance_filtering(self, isolate_lessons):
        mod = isolate_lessons
        mod._save_lesson("AI 智能体", 1, "forge", "AI 相关教训记录")
        mod._save_lesson("跨境电商", 1, "cast", "跨境相关教训记录")
        lessons = mod._load_lessons("AI 智能体")
        assert any("AI" in l.get("topic", "") for l in lessons)

    def test_empty_lesson_skipped(self, isolate_lessons):
        mod = isolate_lessons
        mod._save_lesson("test", 1, "forge", "")
        mod._save_lesson("test", 1, "forge", "短")  # < 8 字符
        lessons = mod._load_lessons("test")
        assert len(lessons) == 0

    def test_lesson_length_capped(self, isolate_lessons):
        mod = isolate_lessons
        mod._save_lesson("test", 1, "forge", "x" * 500)
        lessons = mod._load_lessons("test")
        assert len(lessons[0]["lesson"]) <= 300

    def test_bounded_rotation(self, isolate_lessons):
        mod = isolate_lessons
        for i in range(120):
            mod._save_lesson(f"topic{i}", i, "forge", f"教训编号 {i} 需要足够长度才能通过")
        with open(mod._LESSONS_PATH, encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) <= mod._LESSONS_MAX

    def test_thread_safety(self, isolate_lessons):
        mod = isolate_lessons
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    mod._save_lesson(f"thread{n}", i, "forge", f"线程 {n} 第 {i} 条教训记录")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0
        with open(mod._LESSONS_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)


class TestReflectAndPersist:
    """_reflect_and_persist 提炼逻辑。"""

    def test_stage_failure_generates_lesson(self, flywheel, isolate_lessons):
        mod = isolate_lessons
        from kernel.plugins.content_flywheel import FlywheelCycle
        cycle = FlywheelCycle(
            cycle_id="t1", cycle_num=1, topic="AI 智能体",
            started_at="2026-01-01T00:00:00", ended_at="2026-01-01T00:01:00",
            status="partial",
            stages={
                "forge": {"ok": False, "error": "route_fn 返回 ok=False"},
                "cast": {"ok": True},
                "echo": {"ok": True, "total_count": 10},
                "refine": {"ok": True},
            },
        )
        flywheel._reflect_and_persist(cycle)
        lessons = mod._load_lessons("AI 智能体")
        assert any("forge" in l.get("lesson", "") for l in lessons)

    def test_echo_zero_feedback_generates_lesson(self, flywheel, isolate_lessons):
        mod = isolate_lessons
        from kernel.plugins.content_flywheel import FlywheelCycle
        cycle = FlywheelCycle(
            cycle_id="t2", cycle_num=2, topic="AI 智能体",
            started_at="2026-01-01T00:00:00", ended_at="2026-01-01T00:01:00",
            status="completed",
            stages={
                "forge": {"ok": True},
                "cast": {"ok": True},
                "echo": {"ok": True, "total_count": 0},
                "refine": {"ok": True},
            },
        )
        flywheel._reflect_and_persist(cycle)
        lessons = mod._load_lessons("AI 智能体")
        assert any("0 条反馈" in l.get("lesson", "") for l in lessons)

    def test_all_success_no_lesson(self, flywheel, isolate_lessons):
        mod = isolate_lessons
        from kernel.plugins.content_flywheel import FlywheelCycle
        cycle = FlywheelCycle(
            cycle_id="t3", cycle_num=3, topic="AI 智能体",
            started_at="2026-01-01T00:00:00", ended_at="2026-01-01T00:01:00",
            status="completed",
            stages={
                "forge": {"ok": True},
                "cast": {"ok": True},
                "echo": {"ok": True, "total_count": 50},
                "refine": {"ok": True},
            },
        )
        flywheel._reflect_and_persist(cycle)
        lessons = mod._load_lessons("AI 智能体")
        assert len(lessons) == 0

    def test_partial_cycle_records_bottleneck(self, flywheel, isolate_lessons):
        mod = isolate_lessons
        from kernel.plugins.content_flywheel import FlywheelCycle
        cycle = FlywheelCycle(
            cycle_id="t4", cycle_num=4, topic="AI 智能体",
            started_at="2026-01-01T00:00:00", ended_at="2026-01-01T00:01:00",
            status="partial",
            stages={
                "forge": {"ok": True},
                "cast": {"ok": False, "error": "platform timeout"},
                "echo": {"ok": False, "error": "no data"},
                "refine": {"ok": True},
            },
        )
        flywheel._reflect_and_persist(cycle)
        lessons = mod._load_lessons("AI 智能体")
        assert any("瓶颈" in l.get("lesson", "") for l in lessons)


class TestForgeLessonInjection:
    """_stage_forge 教训注入。"""

    def test_lessons_injected_into_payload(self, isolate_lessons):
        mod = isolate_lessons
        mod._save_lesson("AI 智能体", 1, "forge", "视频时长 60s 太长，建议 30s")

        captured = []

        def mock_route(cap, payload):
            captured.append((cap, payload))
            r = MagicMock()
            r.ok = True
            r.data = {"video_path": "test.mp4", "script": "test"}
            r.error = ""
            return r

        fw = mod.ContentFlywheel(topic="AI 智能体", route_fn=mock_route)
        fw._stage_forge()

        assert len(captured) == 1
        _, payload = captured[0]
        assert "lessons" in payload
        assert any("30s" in l for l in payload["lessons"])

    def test_no_lessons_empty_list(self, isolate_lessons):
        mod = isolate_lessons
        captured = []

        def mock_route(cap, payload):
            captured.append((cap, payload))
            r = MagicMock()
            r.ok = True
            r.data = {}
            r.error = ""
            return r

        fw = mod.ContentFlywheel(topic="全新主题无历史", route_fn=mock_route)
        fw._stage_forge()

        _, payload = captured[0]
        assert payload["lessons"] == []


class TestSkillThinWrapper:
    """Skill 包装层只做委托。"""

    def test_missing_topic(self):
        from skills.content_flywheel_skill import ContentFlywheelSkill
        skill = ContentFlywheelSkill()
        result = skill.execute({})
        assert result["success"] is False
        assert "topic" in result["error"]

    def test_delegates_to_engine(self, isolate_lessons):
        from skills.content_flywheel_skill import ContentFlywheelSkill
        skill = ContentFlywheelSkill(route_fn=None)
        result = skill.execute({"topic": "测试委托", "max_cycles": 1})
        assert result["success"] is True
        assert result["total_cycles"] == 1
        assert result["trace"]["engine"] == "kernel.plugins.content_flywheel.ContentFlywheel"

    def test_format_report(self, isolate_lessons):
        from skills.content_flywheel_skill import ContentFlywheelSkill
        skill = ContentFlywheelSkill(route_fn=None)
        result = skill.execute({"topic": "报告测试", "max_cycles": 1})
        report = skill.format_report(result)
        assert "内容飞轮执行报告" in report
