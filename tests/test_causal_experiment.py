import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""因果实验框架测试。"""
import pytest
from kernel.causal_experiment import CausalExperimentEngine, Experiment


class TestCausalExperimentEngine:
    def setup_method(self):
        self.engine = CausalExperimentEngine()

    def test_should_experiment_no_data(self):
        """无CausalModel时默认需要实验来积累数据。"""
        assert self.engine.should_experiment("web.search") is True

    def test_create_experiment(self):
        """创建实验。"""
        exp = self.engine.create_experiment("web.search", ["baidu", "bing"])
        assert exp.capability == "web.search"
        assert exp.engine_a in ["baidu", "bing"]
        assert exp.engine_b in ["baidu", "bing"]
        assert exp.engine_a != exp.engine_b
        assert exp.status == "running"

    def test_assign_engine(self):
        """分配引擎是A或B之一。"""
        exp = self.engine.create_experiment("web.search", ["baidu", "bing"])
        assigned = self.engine.assign_engine(exp.experiment_id)
        assert assigned in [exp.engine_a, exp.engine_b]

    def test_record_and_analyze(self):
        """记录结果并分析。"""
        exp = self.engine.create_experiment("web.search", ["baidu", "bing"])
        for _ in range(15):
            self.engine.record_outcome(exp.experiment_id, exp.engine_a, True, 100)
            self.engine.record_outcome(exp.experiment_id, exp.engine_b, False, 200)
        result = self.engine.analyze(exp.experiment_id)
        assert "winner" in result
        assert result["winner"] == exp.engine_a
        assert result["p_value"] is not None

    def test_record_nonexistent_experiment(self):
        """记录不存在的实验抛出ValueError。"""
        with pytest.raises(ValueError):
            self.engine.record_outcome("nonexistent", "baidu", True)

    def test_analyze_incomplete_experiment(self):
        """样本不足时分析返回需要更多样本。"""
        exp = self.engine.create_experiment("web.search", ["baidu", "bing"])
        self.engine.record_outcome(exp.experiment_id, exp.engine_a, True)
        result = self.engine.analyze(exp.experiment_id)
        assert "recommendation" in result
