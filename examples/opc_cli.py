"""OPC 商业飞轮 CLI 入口（开箱即用）。

把一人公司通用价值链 分析→宣传→获客→交付→维护/回流 一句话跑起来。
非技术用户也能用：选场景、填业务描述、回车，飞轮自己转。

运行（repo 根目录）:
  # 交互模式（推荐首次使用）
  PYTHONPATH=D:\\AOS\\src python examples/opc_cli.py

  # 命令行直跑（自媒体场景，1 轮，dry-run 先看怎么跑）
  PYTHONPATH=D:\\AOS\\src python examples/opc_cli.py -s content-creator -c 1 --dry-run

  # 真跑（需 .env 配好 LLM/搜索 key，副作用阶段会逐一确认）
  PYTHONPATH=D:\\AOS\\src python examples/opc_cli.py -b "独立顾问，提供 AI 转型咨询" -c 1

  # 跳过副作用确认（危险！仅可信环境用）
  PYTHONPATH=D:\\AOS\\src python examples/opc_cli.py -s content-creator --yes

安全纪律：
- 副作用阶段（获客/交付）默认逐一 input() 确认，--yes 才跳过（会打印警告）。
- --dry-run 完全不触发 autopilot，只打印飞轮将怎么跑。
- 扩展性：加场景 = 在 SCENARIOS 加一条；加阶段 = register_stage(Stage(...))。
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from typing import Any, Callable, Dict, List

# 让脚本在 repo 根直接运行也能找到 src 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.opc_loop import (
    OPCBusinessLoop, OPCLoopConfig, Stage, register_stage,
)


# ---------------------------------------------------------------------------
# 场景预设（扩展性：加场景 = 加一条）
# ---------------------------------------------------------------------------
SCENARIOS: Dict[str, Dict[str, Any]] = {
    "content-creator": {
        "name": "自媒体一人公司",
        "business": "自媒体一人公司，主营 AI/效率类短视频与图文，目标是通过内容获客与变现",
        "stages": None,  # None = 默认全链路
        "note": "内容=产品，宣传≈交付的前置",
    },
    "consultant": {
        "name": "独立顾问",
        "business": "独立顾问，提供企业 AI 转型咨询，通过专业内容获客并交付咨询方案",
        "stages": None,
        "note": "B2B，交付是核心收入环节",
    },
    "ecommerce": {
        "name": "一人电商",
        "business": "一人电商，售卖某品类商品，通过多渠道分发获客并完成订单交付",
        "stages": None,
        "note": "交付=履约，副作用最重",
    },
    "research": {
        "name": "仅研报（最小闭环）",
        "business": "研报服务，输出结构化研究报告",
        "stages": ["analyze", "maintain"],  # 只跑分析+回流，最轻量
        "note": "适合先验证分析能力",
    },
}


# ---------------------------------------------------------------------------
# 可读输出
# ---------------------------------------------------------------------------
def _line(char: str = "─", n: int = 60) -> str:
    return char * n


def _print_stage_header(stage: Stage, cycle: int, dry_run: bool) -> None:
    tag = "[DRY-RUN] " if dry_run else ""
    flag = " ⚠副作用" if stage.side_effect else ""
    print(f"\n{_line()}")
    print(f"轮次 {cycle + 1} · 阶段 [{stage.name}] ({stage.id}){flag}")
    print(f"{tag}能力标签: {stage.capability}  |  并行安全: {stage.parallel_safe}")
    if stage.channels:
        print(f"渠道: {', '.join(stage.channels)}")


def _print_stage_result(ok: bool, skipped: bool, reason: str, duration: float) -> None:
    if skipped:
        print(f"  ⏭ 跳过（{reason}）  [{duration:.1f}s]")
    elif ok:
        print(f"  ✅ 成功  [{duration:.1f}s]")
    else:
        print(f"  ❌ 失败（已记入 Meta-Trace，下轮分析自动参考）  [{duration:.1f}s]")


def _print_summary(result: Dict[str, Any], total_dur: float) -> None:
        print(f"\n{_line('═')}")
        print(f"飞轮完成 · 业务: {result['business']}")
        print(f"总轮次: {result['cycles']}  |  阶段: {' → '.join(result['stages'])}")
        print(f"总耗时: {total_dur:.1f}s")
        confirm_log = result.get("confirm_log", [])
        if confirm_log:
            allowed = sum(1 for c in confirm_log if c["allowed"])
            denied = len(confirm_log) - allowed
            print(f"副作用确认: {allowed} 通过, {denied} 拒绝")
        # 每轮教训数
        for cd in result.get("cycles_detail", []):
            ls = cd.get("lessons_saved", 0)
            stage_summary = []
            for s in cd.get("stages", []):
                if s.get("skipped"):
                    stage_summary.append(f"{s['stage']}⏭")
                elif s.get("ok"):
                    stage_summary.append(f"{s['stage']}✅")
                else:
                    stage_summary.append(f"{s['stage']}❌")
            print(f"  轮 {cd['cycle'] + 1}: {' '.join(stage_summary)}  教训+{ls}")
        print(_line('═'))


# ---------------------------------------------------------------------------
# 可插拔执行器
# ---------------------------------------------------------------------------
def make_dry_run_executor() -> Callable:
    """dry-run：只打印任务文本，不真调 autopilot。"""

    def _exec(stage: Stage, task_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        print(f"  任务文本: {task_text[:200]}{'...' if len(task_text) > 200 else ''}")
        return {"ok": True, "dry_run": True, "stage": stage.id}

    return _exec


def make_real_executor(planner: str) -> Callable:
    """真跑：懒加载 autopilot.run。"""

    def _exec(stage: Stage, task_text: str, ctx: Dict[str, Any]) -> Dict[str, Any]:
        from kernel import autopilot
        return autopilot.run(task_text, planner=planner)

    return _exec


def make_confirm_fn(auto_yes: bool, dry_run: bool) -> Callable:
    """副作用阶段确认。dry_run/auto_yes 直接放行；否则 input() 交互。"""

    def _confirm(stage: Stage, task_text: str) -> bool:
        if dry_run:
            return True
        if auto_yes:
            print(f"  ⚡ --yes 跳过确认")
            return True
        print(f"\n  ⚠ 即将执行副作用阶段 [{stage.name}]")
        print(f"  任务: {task_text[:200]}{'...' if len(task_text) > 200 else ''}")
        try:
            ans = input("  确认执行? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(f"  ⏭ 已拒绝（中断）")
            return False
        if ans not in ("y", "yes"):
            print(f"  ⏭ 已拒绝（跳过该阶段）")
            return False
        return True

    return _confirm


# ---------------------------------------------------------------------------
# 钩子：每阶段结束打印
# ---------------------------------------------------------------------------
def _make_on_stage_end(dry_run: bool):
    def _hook(stage: Stage, result: Any, ctx: Dict[str, Any]) -> None:
        # 真跑时 autopilot.run 返回 dict 含 reflection；dry_run 返回简化结构
        if dry_run:
            return
        if isinstance(result, dict):
            refl = result.get("reflection", {})
            attempts = refl.get("attempts", 0)
            exhausted = refl.get("exhausted", False)
            run_id = result.get("run_id", "—")
            print(f"  run_id: {run_id}  反思尝试: {attempts}  反思耗尽: {exhausted}")

    return _hook


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="opc_cli",
        description="OPC 商业飞轮 CLI —— 一人公司通用价值链常驻环",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="场景预设: " + ", ".join(f"{k}({v['name']})" for k, v in SCENARIOS.items()),
    )
    p.add_argument("-b", "--business", default=None,
                   help="业务描述（自然语言）。不填则交互提示或用 --scenario 预设")
    p.add_argument("-s", "--scenario", default=None, choices=list(SCENARIOS.keys()),
                   help="预设场景（自动填充业务描述与阶段）")
    p.add_argument("-c", "--cycles", type=int, default=1,
                   help="飞轮轮次（默认 1，演示用；生产建议 3+）")
    p.add_argument("--stages", default=None,
                   help="指定阶段，逗号分隔（默认全部：analyze,promote,acquire,deliver,maintain）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印飞轮将怎么跑，不真调 LLM/autopilot")
    p.add_argument("--yes", action="store_true",
                   help="跳过副作用阶段确认（危险！仅可信环境用）")
    p.add_argument("--planner", default="heuristic", choices=["heuristic", "ag2"],
                   help="规划器（默认 heuristic，会主动产并行组；ag2 保守串行）")
    return p


def _resolve_business(args: argparse.Namespace) -> tuple[str, List[str] | None]:
    """解析业务描述与阶段列表。无 business 且无 scenario 时交互提示。"""
    stages: List[str] | None = None
    if args.scenario:
        sc = SCENARIOS[args.scenario]
        business = args.business or sc["business"]
        stages = sc.get("stages")
        print(f"场景: {sc['name']}  |  {sc.get('note', '')}")
    elif args.business:
        business = args.business
    else:
        # 交互模式
        print("=" * 60)
        print("OPC 商业飞轮 · 交互模式")
        print("=" * 60)
        print("可选场景预设:")
        for i, (k, v) in enumerate(SCENARIOS.items(), 1):
            print(f"  {i}. {k} ({v['name']}) - {v.get('note', '')}")
        print(f"  {len(SCENARIOS) + 1}. 自定义输入")
        try:
            choice = input("选择场景编号（回车=自定义）: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
        if choice.isdigit() and 1 <= int(choice) <= len(SCENARIOS):
            key = list(SCENARIOS.keys())[int(choice) - 1]
            sc = SCENARIOS[key]
            business = sc["business"]
            stages = sc.get("stages")
            print(f"已选: {sc['name']}")
        else:
            try:
                business = input("请输入业务描述（一句话）: ").strip()
            except (EOFError, KeyboardInterrupt):
                business = ""
            if not business:
                print("未提供业务描述，退出。")
                sys.exit(1)

    if args.stages:
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    return business, stages


def main(argv: List[str] | None = None) -> Dict[str, Any]:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    business, stages = _resolve_business(args)

    # 安全警告
    if args.yes and not args.dry_run:
        print("⚠️  --yes 已开启：副作用阶段将跳过确认直接执行！")
        print("   仅在你完全信任环境与业务描述时使用。")
    if args.dry_run:
        print("🔸 DRY-RUN 模式：只打印飞轮将怎么跑，不真调 LLM。")

    # 构造执行器/确认函数
    executor = make_dry_run_executor() if args.dry_run else make_real_executor(args.planner)
    confirm_fn = make_confirm_fn(auto_yes=args.yes, dry_run=args.dry_run)

    cfg = OPCLoopConfig(
        business=business,
        enabled_stage_ids=stages,
        max_cycles=args.cycles,
        planner=args.planner,
        executor=executor,
        confirm_fn=confirm_fn,
        on_stage_end=_make_on_stage_end(args.dry_run),
    )

    loop = OPCBusinessLoop(cfg)

    # 包装 executor 打印进度（opc_loop 只暴露 on_stage_end 后置钩子，
    # 前置 header 最干净是包在 executor 外层）
    base_executor = executor

    def _decorated_executor(stage: Stage, task_text: str, ctx: Dict[str, Any]) -> Any:
        _print_stage_header(stage, ctx.get("cycle", 0), args.dry_run)
        t0 = time.time()
        res = base_executor(stage, task_text, ctx)
        dur = time.time() - t0
        ok = OPCBusinessLoop._is_ok(res)
        _print_stage_result(ok=ok, skipped=False, reason="", duration=dur)
        return res

    cfg.executor = _decorated_executor

    print(f"\n🚀 启动 OPC 飞轮: {business[:80]}{'...' if len(business) > 80 else ''}")
    print(f"   轮次: {args.cycles}  |  规划器: {args.planner}  |  阶段: {stages or '全链路'}")

    t_start = time.time()
    result = loop.run()
    total_dur = time.time() - t_start

    _print_summary(result, total_dur)
    return result


if __name__ == "__main__":
    main()
