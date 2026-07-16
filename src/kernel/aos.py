"""AOS 统一自主入口：一句话 → 意图 → 环境 → 多方案 → 执行 → 汇报。

设计铁律（灵活 / 不绑定任务类型）：
  - 不把任务分类成 video/install/deploy/... 的硬编码分支；
  - 任何人给的任意任务都走同一条管道：意图解读 → 环境探测 →
    LLM 生成多套差异化方案 → 选方案 → autopilot 真执行（sandbox 限额）→
    检测产出文件并汇报；
  - 执行层只认「能力」（搜索 / 代码执行 / 推理），由 LLM 规划器决定怎么组合，
    因此「每个人想弄的都不一样」也能接住。

用法:
  python -m kernel.aos "研究 SQLite 与 PostgreSQL 的核心区别，写对比要点到 D:/AOS/_output/db_compare.md"
  python -m kernel.aos --auto "..."          # 不交互，直接选推荐方案(0)执行
  python -m kernel.aos --plan 1 "..."        # 指定方案索引
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _load_env() -> None:
    """尽量加载项目 .env（不影响无 key 时的回落路径）。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    except Exception:
        pass


def _snapshot_output_dirs() -> dict:
    """快照输出目录现有文件，供运行后对比，只认【本次新产生】的产出。"""
    roots = [
        os.path.join(os.path.dirname(__file__), "..", "..", "_output"),
        os.path.join(os.path.dirname(__file__), "..", "..", "_video_output"),
    ]
    snap = {}
    for root in roots:
        if os.path.isdir(root):
            try:
                snap[root] = set(os.listdir(root))
            except OSError:
                snap[root] = set()
    return snap


def _scan_output_artifacts(snapshot: dict) -> list:
    """只回报本次运行【新产生】的文件（快照对比），避免把历史遗留文件误报为产出。

    不预设只认视频——研究报告的 .md / 数据的 .csv / 媒体的 .mp4 一视同仁。
    """
    arts = []
    for root, before in snapshot.items():
        if not os.path.isdir(root):
            continue
        try:
            now = set(os.listdir(root))
        except OSError:
            continue
        for name in now:
            if name in before:
                continue
            fp = os.path.join(root, name)
            if os.path.isfile(fp):
                arts.append({"type": "file", "path": fp})
    return arts


def run_task(task: str, auto: bool = False, plan_idx: int | None = None) -> dict:
    """执行一个完整自主任务，返回结构化结果。

    Args:
        task:     用户的一句话任务（任意类型）
        auto:     不交互，直接选推荐方案(索引0)执行
        plan_idx: 指定方案索引（优先于 auto）
    """
    from kernel.workflow_engine import (
        analyze_intent,
        probe_environment,
        generate_plans,
    )
    from kernel.autopilot import run as autopilot_run

    # 1) 意图解读（灵活，无任务类型分支；仅轻量 category_hint 供 LLM 参考）
    env = probe_environment()
    intent = analyze_intent(task, env)
    if intent.get("needs_clarification"):
        if auto:
            # 自主模式：路径扫描等误触发澄清（如任务里的输出路径含 D:）时，
            # 直接以用户原目标继续，不阻塞「一句话就干」。
            intent["needs_clarification"] = False
            intent["goal"] = task
        else:
            return {
                "status": "clarify",
                "question": intent.get("clarification_question", ""),
            }

    # 2) 多方案提案（LLM 生成 3+ 套差异化，无 key 回落通用模板）
    plans = generate_plans(intent, env)
    if not plans:
        return {"status": "error", "error": "无法生成任何方案"}

    # 3) 选方案
    if plan_idx is not None:
        idx = plan_idx
    elif auto:
        idx = 0
    else:
        print("\n📋 可用方案:")
        for i, p in enumerate(plans):
            extra = ""
            missing = p.get("missing_tools", [])
            if missing:
                extra = f"  ⚠️ 需先装: {', '.join(missing)}"
            print(f"  [{i}] {p['name']}: {p.get('approach', '')[:90]}{extra}")
        raw = input("\n选方案（索引，默认 0）: ").strip()
        idx = int(raw) if raw.isdigit() else 0
    if not (0 <= idx < len(plans)):
        idx = 0

    # 4) 执行（走 sandbox-backed 的 autopilot 真执行，不假成功）
    #    执行前快照输出目录，运行后只认【新产生】的文件，避免把历史遗留误报为产出。
    snapshot = _snapshot_output_dirs()
    chosen = plans[idx]
    plan_text = chosen.get("name", f"方案{idx}")
    steps_text = "\n".join(chosen.get("steps", []))
    exec_task = f"{intent.get('goal', task)}\n推荐方案: {plan_text}\n步骤:\n{steps_text}"

    result = autopilot_run(exec_task, planner="ag2")

    # 5) 产出文件检测（只认本次运行新产生的文件，任何类型都一视同仁汇报）
    artifacts = _scan_output_artifacts(snapshot)

    return {
        "status": "done",
        "intent": intent,
        "plans": plans,
        "chosen_index": idx,
        "result": result,
        "artifacts": artifacts,
    }


def _print_report(r: dict) -> None:
    if r.get("status") == "clarify":
        print("\n❓ 需要补充信息:\n" + r["question"])
        return
    if r.get("status") == "error":
        print("\n❌ " + r.get("error", "未知错误"))
        return

    result = r["result"]
    exe = result.get("execution", {})
    conf = result.get("confidence", {})
    print("\n" + "=" * 60)
    print(f"任务: {result.get('task', '')[:80]}")
    print(f"规划器: {result.get('planner')} | 耗时: {result.get('duration_s')}s")
    print(f"执行: {exe.get('ok_steps', 0)} 步成功 / {exe.get('failed_steps', 0)} 步失败")
    if conf:
        print(f"置信度: {conf.get('label')} ({conf.get('metrics', {}).get('success_rate', '?')})")
    print("=" * 60)

    for i, t in enumerate(exe.get("trace", [])):
        ok = "✅" if t.get("ok") else "❌"
        summary = str(t.get("summary") or "")[:140].replace("\n", " ")
        print(f"  {i + 1}. [{t.get('capability')}] {ok} {summary}")

    if r.get("artifacts"):
        print("\n📦 产出文件:")
        for a in r["artifacts"]:
            print(f"  - {a['path']}")
    final = exe.get("final")
    if final:
        print(f"\n📤 最终产出: {str(final)[:400]}")

    # 诚实校验：声称有产出文件，但磁盘上不存在 → 明确提示
    for a in r.get("artifacts", []):
        if not os.path.exists(a["path"]):
            print(f"  ⚠️ 产出文件不存在（执行未真正落盘）: {a['path']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="AOS 统一自主入口：一句话 → 自己干")
    ap.add_argument("task", nargs="*", help="一句话任务（任意类型）")
    ap.add_argument("--auto", action="store_true", help="不交互，直接选推荐方案执行")
    ap.add_argument("--plan", type=int, default=None, help="指定方案索引")
    args = ap.parse_args()

    _load_env()

    task = " ".join(args.task).strip()
    if not task:
        task = input("🎯 任务: ").strip()
    if not task:
        print("任务不能为空")
        sys.exit(1)

    r = run_task(task, auto=args.auto, plan_idx=args.plan)
    _print_report(r)


if __name__ == "__main__":
    main()
