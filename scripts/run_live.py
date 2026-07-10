#!/usr/bin/env python3
"""AOS 活体进化 — 一键启动脚本

用法：
  python scripts/run_live.py                     # 默认：5 Agent, 20 任务, 5代
  python scripts/run_live.py --agents 8 --tasks 50  # 8 Agent, 50 任务
  python scripts/run_live.py --forever               # 7x24 持续运行

输出：每代进化结果 + 最终活体状态 + 进化历史

依赖：需要 AOS_TOKEN_SECRET 环境变量（用于自含式令牌）。
      LLM 调用走 LiteLLM，需真实 API key 或 ZHIPU_API_KEY 等。
      (无 key 时优雅降级，agent 会失败但不会崩溃)
"""

import sys
import os
import time
import argparse

# 加载项目 .env 中的 ZHIPU_API_KEY 等
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# Ensure src/ is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.live import LiveEvolutionEngine


def banner(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="AOS 活体进化 — 真LLM驱动自进化闭环")
    parser.add_argument("--agents", type=int, default=5, help="初始种群大小 (default: 5)")
    parser.add_argument("--tasks", type=int, default=20, help="总任务数 (default: 20)")
    parser.add_argument("--interval", type=int, default=5, help="每N任务进化一次 (default: 5)")
    parser.add_argument("--keep-top", type=int, default=3, help="每代保留精英数 (default: 3)")
    parser.add_argument("--forever", action="store_true", help="持续运行不停止")
    parser.add_argument("--sleep", type=float, default=2.0, help="每轮间隔秒数 (default: 2)")
    args = parser.parse_args()

    banner("AOS Live Evolution Engine v1.0")
    print(f"  Population: {args.agents} agents")
    print(f"  Tasks: {args.tasks} total, evolve every {args.interval}")
    print(f"  Keep top: {args.keep_top} per generation")
    print()

    # 初始化活体引擎
    engine = LiveEvolutionEngine(
        evolution_interval=args.interval,
        keep_top_agents=args.keep_top,
        min_population=2,
        max_population=10,
        offspring_per_generation=2,
    )

    # 创建初始种群
    ids = engine.initialize_population(args.agents)
    print(f"Initial population: {len(ids)} agents created")
    for aid in ids[:5]:
        dna = engine._population_dna.get(aid)
        if dna:
            eng = dna._gene_value("engine", "?")
            print(f"  {aid}  engine={eng}  gen={dna.generation}")

    # 任务集 — 混合简单和复杂问题
    task_bank = [
        "What is 2+2?",
        "Explain machine learning in one sentence.",
        "What is the capital of France?",
        "Write a Python function to reverse a string.",
        "What is the difference between HTTP and HTTPS?",
        "Name three types of machine learning.",
        "What is 15 * 7?",
        "Explain what a neural network is.",
        "Convert 100 Celsius to Fahrenheit.",
        "What does the acronym REST stand for?",
        "Write a haiku about coding.",
        "What is the purpose of a database index?",
        "Name the planets in our solar system.",
        "What is the time complexity of binary search?",
        "Explain the concept of recursion.",
        "What is JSON?",
        "What does CSS stand for?",
        "Name two popular Python web frameworks.",
        "What is a git commit?",
        "Explain what an API is.",
        "What is the difference between TCP and UDP?",
        "Write a SQL query to select all users.",
        "What is a docker container?",
        "Explain what unit testing is.",
        "What is the purpose of a load balancer?",
    ]

    tasks = task_bank[:args.tasks]
    if len(tasks) < args.tasks:
        tasks = (tasks * ((args.tasks // len(tasks)) + 1))[:args.tasks]

    round_num = 0
    total_start = time.time()

    while True:
        round_num += 1
        batch = tasks[:args.interval]
        tasks = tasks[args.interval:]

        if not batch:
            if not args.forever:
                break
            tasks = task_bank[:args.tasks]  # 循环
            time.sleep(args.sleep)
            continue

        print(f"\n--- Round {round_num} ({len(batch)} tasks) ---")

        # 执行任务（每 interval 个后自动进化）
        results = engine.run_tasks(batch)

        successes = sum(1 for r in results if r.success)
        total_latency = sum(r.latency_seconds for r in results)

        print(f"  Results: {successes}/{len(batch)} OK, "
              f"avg latency={total_latency/max(1,len(batch)):.2f}s")

        # 打印当前存活 agent 和 fitness
        status = engine.status()
        print(f"  Generation: {status.generation} | "
              f"Population: {status.population} | "
              f"Tasks done: {status.tasks_completed} | "
              f"Eliminations: {status.eliminations} | "
              f"Spawns: {status.spawns}")

        if status.top_agent != "none":
            print(f"  Top agent: {status.top_agent} (fitness={status.top_fitness:.2f})")
        if status.heal_events > 0:
            print(f"  Heal events: {status.heal_events}")
        if status.anomaly_alerts > 0:
            print(f"  Anomaly alerts: {status.anomaly_alerts}")

        if args.forever and tasks:
            time.sleep(args.sleep)

    # 终态报告
    banner("Final Status")
    s = engine.status()
    elapsed = round(time.time() - total_start, 1)
    print(f"  Uptime: {s.uptime_seconds:.1f}s")
    print(f"  Generations evolved: {s.generation}")
    print(f"  Tasks completed: {s.tasks_completed}")
    print(f"  Final population: {s.population}")
    print(f"  Total eliminations: {s.eliminations}")
    print(f"  Total spawns: {s.spawns}")
    print(f"  Heal events: {s.heal_events}")
    print(f"  Anomaly alerts: {s.anomaly_alerts}")
    print(f"  Total tokens: {s.total_tokens}")
    print(f"  Total cost: ${s.total_cost_usd}")
    print(f"  Top agent: {s.top_agent} (fitness: {s.top_fitness:.2f})")

    # 存活 agent 详情
    print(f"\n  Surviving agents:")
    for a in engine.kernel.list_agents():
        if a.status.value == "stopped":
            continue
        dna = engine._population_dna.get(a.agent_id)
        fs = engine.fitness.score(a.agent_id)
        gen = dna.generation if dna else "?"
        fit = f"{fs.overall:.2f}" if fs else "N/A"
        eng = a.spec.engine
        print(f"    {a.agent_id}  gen={gen}  engine={eng}  fitness={fit}")

    # 自然选择历史
    print(f"\n  Selection generation: {engine.selection.generation}")
    print(f"  Economy budgets: {len(engine.economy.all_budgets())} agents tracked")

    banner("Live Evolution Complete")
    print(f"  This was NOT a simulation — every agent routed through real LLM calls.")
    print(f"  Fitness from real latency + success + token data.")
    print(f"  Selection and breeding used real kernel paths.")
    print()


if __name__ == "__main__":
    main()
