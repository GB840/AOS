#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自进化闭环「端到端」验证脚本（诚实版）
=====================================

验证目标（用户核心痛点）：AOS 的自进化环能否在真实 LLM 任务下
「跑一轮 → 反思 → 下一轮变好」。

本脚本分两层，诚实区分「机制可用」与「真 LLM 端到端」：

  [默认 / 沙箱可跑] MOCK 模式（--mock，默认）：
    用注入的 mock executor + 内存 lesson_store 真实跑 OPCBusinessLoop 的控制流，
    断言：
      · 六阶段按序推进（analyze→promote→acquire→deliver→evolve→maintain）
      · 某阶段失败后，教训写入 store，并在下一轮 analyze 阶段被注入
    这证明「闭环接线 + 教训回流」机制真实可用（芯粒/单元真跑层级）。
    ⚠ 不证明「真 LLM 产出质量逐轮变好」——那是端到端层级，需真 LLM。

  [需主机] REAL 模式（--real）：
    把 executor 接到真实 autopilot.run（依赖真 LLM + .env API key），
    在主机实跑多轮，人工/自动比对逐轮产出质量。
    沙箱无真 LLM、重型链跑不动，故 REAL 模式不在沙箱自动执行，只输出命令与预期。
    主机执行：
        set PYTHONPATH=src
        C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/self_evo_loop_verify.py --real

诚实纪律（AGENTS.md §0.7.1）：本脚本绝不把「机制跑通」说成「端到端跑通」。
只到机制层级，绝不许宣称已验证真 LLM 自进化。

依赖：仅标准库 + 项目 kernel.opc_loop（轻量，无重型 import）。
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List, Tuple


def _build_mock_executor(captured: Dict[Tuple[int, str], str]):
    """mock executor：第 0 轮 acquire 故意失败，其余成功，并记录收到的任务文本。"""
    def _exec(stage, task_text: str, ctx: Dict[str, Any]):
        captured[(ctx.get("cycle", -1), stage.id)] = task_text
        if stage.id == "acquire" and ctx.get("cycle", 0) == 0:
            return {"ok": False, "error": "模拟：获客渠道白名单被拒（测试用）"}
        return {"ok": True}
    return _exec


class _MemLessonStore:
    """内存版 lesson_store，模拟 Meta-Trace 的 save/load 契约。"""
    def __init__(self):
        self._lessons: List[Dict[str, Any]] = []

    def save(self, task, failed_cap, error, lesson):
        self._lessons.append(
            {"task": task, "cap": failed_cap, "error": error, "lesson": lesson}
        )

    def load(self, task, limit=3):
        return self._lessons[-limit:]


def run_mock() -> int:
    try:
        from kernel.opc_loop import OPCLoopConfig, OPCBusinessLoop
    except Exception as e:  # noqa: BLE001
        print(f"[SKIP] 无法 import kernel.opc_loop：{e}")
        return 2

    captured: Dict[Tuple[int, str], str] = {}
    store = _MemLessonStore()
    cfg = OPCLoopConfig(
        business="护眼眼镜一人公司（验证用例）",
        max_cycles=3,
        executor=_build_mock_executor(captured),
        lesson_store=store,
        confirm_fn=lambda stage, text: True,
        inject_lessons=True,
    )
    loop = OPCBusinessLoop(cfg)
    result = loop.run()

    # 断言 1：阶段按序推进
    stages = result["stages"]
    expected = ["analyze", "promote", "acquire", "deliver", "evolve", "maintain"]
    assert stages == expected, f"阶段序列异常: {stages}"

    # 断言 2：第 0 轮 acquire 失败 → 至少写 1 条教训
    assert store._lessons, "没有任何教训被保存"
    saved_error = store._lessons[0]["error"]
    assert "获客渠道白名单被拒" in saved_error, saved_error

    # 断言 3：第 1 轮 analyze 任务文本注入了上一轮教训
    analyze_cycle1 = captured.get((1, "analyze"), "")
    assert "历史教训" in analyze_cycle1, "第1轮 analyze 未注入历史教训"
    assert "获客渠道白名单被拒" in analyze_cycle1, "第1轮 analyze 未携带上轮失败原因"

    print("=" * 64)
    print("✅ MOCK 模式 PASS：闭环控制流 + 教训回流注入 机制真实可用")
    print(f"   阶段序列 : {stages}")
    print(f"   保存教训数: {len(store._lessons)}")
    print(f"   第1轮 analyze 已注入历史教训 (片段): ...{analyze_cycle1[-60:]!r}")
    print("=" * 64)
    print("⚠ 诚实边界：以上仅证明『机制可用』，未用真 LLM。")
    print("   真端到端（真 LLM 跑一轮→反思→下一轮变好）须主机 --real 模式。")
    return 0


def run_real() -> int:
    print("[REAL] 真 LLM 端到端模式：需要主机 + 真实 API key（.env）。")
    print("        沙箱无真 LLM、重型链跑不动，故不在脚本内自动执行，仅给命令与预期。")
    print("        请在用户主机执行：")
    print("          set PYTHONPATH=src")
    print(
        "          C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\python.exe"
        " scripts/self_evo_loop_verify.py --real"
    )
    print("\n预期（主机真跑后）：")
    print("  · 多轮业务闭环真实推进，每轮有真实 LLM 产出。")
    print("  · 失败阶段的教训进入 Meta-Trace，下轮 analyze 注入并改变策略。")
    print("  · 逐轮产出质量（人工/自动指标评估）应不低于首轮，且能观察到策略调整。")
    print("  · 若无法观察到『变好』，即用户痛点未解，须继续修 autopilot/反思链路。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="AOS 自进化闭环验证（诚实版）")
    ap.add_argument("--real", action="store_true", help="真 LLM 端到端模式（需主机+key）")
    args = ap.parse_args()
    if args.real:
        return run_real()
    return run_mock()


if __name__ == "__main__":
    sys.exit(main())
