"""跨境合规智能体测试。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skills.crossborder_compliance import (  # noqa: E402
    CrossBorderAgent,
    COMPLIANCE_DB,
)


@pytest.fixture
def agent():
    return CrossBorderAgent()


class TestComplianceDB:
    def test_rules_defined(self):
        assert len(COMPLIANCE_DB) >= 25
        for item in COMPLIANCE_DB:
            assert item.item_id
            assert item.country in ("DE", "US", "UK", "JP", "AU", "ALL")
            assert item.severity in ("mandatory", "recommended", "conditional")

    def test_covers_major_markets(self):
        countries = {item.country for item in COMPLIANCE_DB}
        assert "DE" in countries
        assert "US" in countries
        assert "JP" in countries


class TestCrossBorderAgent:
    def test_bluetooth_to_germany(self, agent):
        result = agent.execute({
            "product": "TWS蓝牙耳机，含锂电池，2.4GHz",
            "destination": "DE",
            "existing_certs": ["CE"],
        })
        assert result["ok"] is True
        assert result["risk_level"] in ("HIGH", "MEDIUM", "LOW", "COMPLIANT")
        assert len(result["requirements"]) > 0
        # CE 已有，不应在缺口中
        gap_ids = [g["id"] for g in result["gaps"]]
        assert "EU01" not in gap_ids  # CE 已满足

    def test_toy_to_us(self, agent):
        result = agent.execute({
            "product": "儿童积木玩具，3岁以上，塑料",
            "destination": "US",
        })
        assert result["ok"] is True
        # 儿童产品应触发 CPSIA
        req_ids = [r["id"] for r in result["requirements"]]
        assert "US06" in req_ids

    def test_led_to_japan(self, agent):
        result = agent.execute({
            "product": "LED灯带，含电源适配器",
            "destination": "JP",
        })
        assert result["ok"] is True
        req_ids = [r["id"] for r in result["requirements"]]
        assert "JP01" in req_ids  # PSE

    def test_missing_product(self, agent):
        result = agent.execute({"destination": "DE"})
        assert result["ok"] is False

    def test_missing_destination(self, agent):
        result = agent.execute({"product": "蓝牙耳机"})
        assert result["ok"] is False

    def test_trace_completeness(self, agent):
        result = agent.execute({
            "product": "无线充电器",
            "destination": "US",
        })
        steps = result["trace"]["steps"]
        step_names = [s["step"] for s in steps]
        assert "category_identify" in step_names
        assert "requirements_match" in step_names
        assert "gap_analysis" in step_names
        assert "risk_assess" in step_names
        assert "action_plan" in step_names

    def test_action_plan_ordered(self, agent):
        result = agent.execute({
            "product": "蓝牙音箱，含锂电池",
            "destination": "DE",
            "channel": "amazon",
        })
        plan = result["action_plan"]
        # 行动计划非空
        assert len(plan) > 0
        # 平台要求应在计划中
        assert any("amazon" in a.get("action", "").lower() for a in plan)


class TestLessons:
    def test_save_and_load(self, agent, tmp_path):
        agent._lessons_path = tmp_path / "lessons.jsonl"
        agent.save_lesson("德国海关严查 WEEE 注册号", "DE/电子产品")
        lessons = agent._load_lessons()
        assert len(lessons) == 1
        assert "WEEE" in lessons[0]["lesson"]
