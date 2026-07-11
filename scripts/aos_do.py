#!/usr/bin/env python
"""
aos-do — AOS 一句话入口

用法:
    python scripts/aos_do.py "你的需求"

核心理念:
    用户说一句话 → AOS 自己知道需要什么组件 → 自动组合 → 关键环节确认 → 执行

示例:
    python scripts/aos_do.py "帮我审查 src/ 的代码，重点关注安全问题"
    python scripts/aos_do.py "分析一下 docs/ 目录的文档结构"
    python scripts/aos_do.py "让架构师和安全专家讨论一下微服务拆分方案"
    python scripts/aos_do.py "审查代码" --target src/kernel/ --focus security
    python scripts/aos_do.py "..." --auto-confirm  # 跳过确认直接执行

记住用户:
    python scripts/aos_do.py "审查代码" --user alice
    # 下次 alice 说"审查代码"，AOS 记得她上次审的是 src/，偏好安全审查
"""

import os
import sys
import argparse
import logging

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aos-do")


def main():
    parser = argparse.ArgumentParser(
        description="AOS 一句话入口 — 说一句话，自动组合组件，确认后执行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
核心理念:
  用户说一句话 → AOS 自己知道需要什么组件 → 自动组合 → 关键环节确认 → 执行

示例:
  python scripts/aos_do.py "帮我审查 src/ 的代码，重点关注安全问题"
  python scripts/aos_do.py "分析一下 docs/ 目录的文档结构"
  python scripts/aos_do.py "让架构师和安全专家讨论微服务拆分方案"
  python scripts/aos_do.py "审查代码" --auto-confirm
        """,
    )
    parser.add_argument("request", nargs="?", default="", help="你的需求（自然语言）")
    parser.add_argument("--target", "-t", default=None, help="目标目录/文件")
    parser.add_argument("--focus", "-f", default=None, help="关注重点: security/performance/style/architecture")
    parser.add_argument("--roles", "-r", default=None, help="角色，逗号分隔")
    parser.add_argument("--user", "-u", default="default", help="用户 ID（用于记忆偏好）")
    parser.add_argument("--auto-confirm", "-y", action="store_true", help="跳过确认，直接执行")
    parser.add_argument("--explain-only", "-e", action="store_true", help="只展示计划，不执行")
    parser.add_argument("--output", "-o", default=None, help="报告输出路径")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    # 交互模式：如果没有传 request，提示输入
    request = args.request
    if not request:
        print("\n  AOS 智能编排器")
        print("  说一句话，告诉我你想做什么：")
        print("  (输入 '?' 查看示例, 输入 'quit' 退出)\n")
        while True:
            try:
                request = input("  > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  再见!")
                sys.exit(0)

            if not request:
                continue
            if request.lower() in ("quit", "exit", "q"):
                print("  再见!")
                sys.exit(0)
            if request == "?":
                print("""
  示例:
    "帮我审查 src/ 的代码，重点关注安全问题"
    "分析一下 docs/ 目录的文档结构"
    "让架构师和安全专家讨论微服务拆分方案"
    "审查代码"  ← AOS 记得你上次审的目录和偏好
""")
                continue
            break

    if not request:
        print("错误: 请提供需求描述", file=sys.stderr)
        sys.exit(1)

    # 追加命令行参数到 request
    if args.target:
        request += f" 目标:{args.target}"
    if args.focus:
        request += f" 关注:{args.focus}"
    if args.roles:
        request += f" 角色:{args.roles}"

    print(f"\n{'='*60}")
    print(f"  AOS 智能编排器")
    print(f"  用户: {args.user}")
    print(f"  需求: {request[:60]}{'...' if len(request) > 60 else ''}")
    print(f"{'='*60}")

    from capabilities.intelligent_orchestrator import get_orchestrator

    orchestrator = get_orchestrator()

    # 1. 理解意图，生成计划
    print(f"\n  🤔 正在理解你的需求...")
    plan = orchestrator.understand(request, user_id=args.user)

    if not plan.steps:
        print(f"\n  ❌ 无法理解你的需求，请换个说法或提供更多信息")
        sys.exit(1)

    # 2. 展示计划
    print(orchestrator.format_plan_for_user(plan))

    if args.explain_only:
        print(f"\n  (仅展示计划，未执行)")
        sys.exit(0)

    # 3. 确认
    if not args.auto_confirm:
        print(f"\n  {'─'*50}")
        has_critical = any(s.requires_confirmation for s in plan.steps)
        if has_critical:
            print(f"  ⚠️  有步骤需要确认。输入 'yes' 确认执行，'no' 取消：")
        else:
            print(f"  输入 'yes' 确认执行，'no' 取消，或直接回车确认：")

        try:
            confirm = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消")
            sys.exit(0)

        if confirm == "no":
            print("  已取消")
            sys.exit(0)
        if confirm not in ("yes", "y", ""):
            print(f"  未知输入 '{confirm}'，已取消")
            sys.exit(0)

    # 4. 执行
    print(f"\n  🚀 正在执行...")
    result = orchestrator.execute(plan, user_id=args.user, skip_confirm=args.auto_confirm)

    if result.get("pending_confirmation"):
        print(f"\n  ⚠️ 步骤需要确认，请使用 --auto-confirm 或重新运行")
        sys.exit(1)

    # 5. 结果
    print(f"\n{'='*60}")
    if result["success"]:
        print(f"  ✅ 执行成功!")
    else:
        print(f"  ⚠️ 部分完成")
        if result.get("errors"):
            for e in result["errors"]:
                print(f"  ❌ {e}")
    print(f"  耗时: {result.get('duration_seconds', 0)}s")
    print(f"{'='*60}\n")

    # 如果有报告，打印路径
    for step_id, step_result in result.get("results", {}).items():
        if isinstance(step_result, dict) and step_result.get("report"):
            print(f"  📄 报告: {step_result['report']}")

    # 退出码
    if not result["success"]:
        sys.exit(1)


if __name__ == "__main__":
    main()