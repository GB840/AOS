"""L2 柔性目标演化引擎 单测（诚实度 ②）"""
from kernel.goal_evolution import Goal, GoalEvolution, GoalStatus


def _goals():
    return [Goal(text="写报告", priority=0.6), Goal(text="学钓鱼", priority=0.3)]


def test_promote_on_success():
    ge = GoalEvolution()
    goals = _goals()
    ge.evolve(goals, {"text": "写报告", "ok": True})
    g = [x for x in goals if x.text == "写报告"][0]
    assert g.successes == 1
    assert g.priority > 0.6


def test_shelve_after_3_failures():
    ge = GoalEvolution()
    goals = [Goal(text="难事", priority=0.6)]
    for _ in range(3):
        ge.evolve(goals, {"text": "难事", "ok": False})
    g = goals[0]
    assert g.failures == 3
    assert g.status == GoalStatus.SHELVED


def test_swap_on_stale():
    ge = GoalEvolution()
    goals = [Goal(text="老目标", priority=0.15)]
    ge.evolve(goals)  # age=1
    for _ in range(12):
        ge.evolve(goals)
    assert goals[0].status == GoalStatus.SWAPPED
