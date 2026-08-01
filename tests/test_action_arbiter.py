"""L6 行动规划仲裁器 单测（诚实度 ②）"""
from kernel.action_arbiter import ActionArbiter, ActionPlan, Verdict


def test_harm_always_blocked():
    a = ActionArbiter()
    v = a.judge(ActionPlan("关掉电闸", risk="low", physical=True, harm_potential=True))
    assert v == Verdict.BLOCK


def test_physical_high_blocked():
    a = ActionArbiter()
    v = a.judge(ActionPlan("启动机械臂", risk="high", physical=True))
    assert v == Verdict.BLOCK


def test_physical_mid_confirm():
    a = ActionArbiter()
    v = a.judge(ActionPlan("开窗帘", risk="mid", physical=True))
    assert v == Verdict.CONFIRM


def test_digital_low_auto():
    a = ActionArbiter()
    v = a.judge(ActionPlan("整理文件", risk="low", physical=False))
    assert v == Verdict.AUTO
