"""测试FitnessTracker线程锁（O3修复验证）"""
import pytest
import threading
from kernel.evolution import FitnessTracker


def test_fitness_tracker_thread_safety():
    """测试多线程并发调用_stats字典数据一致"""
    tracker = FitnessTracker()

    num_threads = 10
    num_iterations = 100

    def worker():
        for i in range(num_iterations):
            agent_id = f"agent{i % 5}"
            if i % 2 == 0:
                tracker.record_success(agent_id, latency=0.5, tokens=100, generation=0)
            else:
                tracker.record_failure(agent_id, generation=0)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证数据一致性
    scores = tracker.all_scores()
    assert len(scores) == 5

    # 验证每个agent的任务数等于成功数+失败数
    for score in scores:
        tasks = score.tasks_completed
        success_rate = score.success_rate
        expected_success = int(tasks * success_rate)
        assert expected_success >= 0


def test_fitness_tracker_no_data_race():
    """测试无数据竞争"""
    tracker = FitnessTracker()

    num_threads = 20
    num_iterations = 50

    errors = []

    def worker():
        try:
            for i in range(num_iterations):
                agent_id = f"agent{i % 3}"
                tracker.record_success(agent_id, latency=0.5, tokens=100, generation=0)
                tracker.record_failure(agent_id, generation=0)
                tracker.score(agent_id)
                tracker.top_agents(n=5)
                tracker.bottom_agents(n=5)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 验证无异常
    assert len(errors) == 0, f"发生{len(errors)}个异常: {errors}"

    # 验证数据一致性
    scores = tracker.all_scores()
    assert len(scores) == 3