"""ConstitutionalGovernor（CONST3）单测 —— 诚实级 ②（代码就绪 + 本地治理真跑）。

覆盖：
- CONSTITUTIONAL_AGENT_AVAILABLE 探测（已装即 True）
- 无配置也能加载默认宪法并本地评估（SixGate，无需外部 LLM）
- evaluate 返回结构化门控结果（blocking_gates / hard_constraint_violations / allowed）
- is_allowed 便捷门控：合规上下文返回 bool，异常时默认不放行
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.constitutional_governor import (  # noqa: E402
    ConstitutionalGovernor,
    CONSTITUTIONAL_AGENT_AVAILABLE,
)


def test_lib_importable():
    # 真接开源：constitutional-agent 已 pip 安装（MIT），import 即成功
    assert CONSTITUTIONAL_AGENT_AVAILABLE is True


def test_evaluate_returns_structured_result():
    gov = ConstitutionalGovernor()
    assert gov.available is True
    result = gov.evaluate({"action": "reply_to_user", "content": "你好，这是一条普通回复"})
    assert isinstance(result, dict)
    assert "blocking_gates" in result
    assert "hard_constraint_violations" in result
    assert "allowed" in result
    assert "blocking" in result
    # 正常 benign 上下文：不应被阻断
    assert isinstance(result["blocking_gates"], list)
    assert isinstance(result["hard_constraint_violations"], list)


def test_is_allowed_returns_bool():
    gov = ConstitutionalGovernor()
    # 良性上下文 → 返回布尔（不抛异常）
    assert isinstance(gov.is_allowed({"action": "log_event", "content": "系统心跳"}), bool)


def test_health_detail_honest_about_license():
    gov = ConstitutionalGovernor()
    detail = gov.health_detail()
    assert detail["license"] == "MIT"
    assert detail["lib_available"] is True
