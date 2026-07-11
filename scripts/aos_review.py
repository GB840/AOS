#!/usr/bin/env python
"""
aos-review — AOS 代码审查流水线

用法:
    python scripts/aos_review.py <target_dir> [options]

示例:
    python scripts/aos_review.py src/                        # 审查 src/ 目录
    python scripts/aos_review.py src/ --no-parallel           # 串行审查
    python scripts/aos_review.py src/ --auto-fix              # 自动修复
    python scripts/aos_review.py src/ --no-tests              # 跳过测试
    python scripts/aos_review.py src/ --output report.md      # 指定报告路径
    python scripts/aos_review.py src/ --model zhipu           # 使用智谱模型
    python scripts/aos_review.py src/ --model local           # 使用本地模型

组件组合:
    LLM 推理 (云端/本地) → 审查代码
    SandboxManager       → 运行测试
    WorkspaceManager     → 文件操作
    ThreadPoolExecutor   → 并行审查
    Markdown 报告        → 输出结果
"""

import os
import sys
import argparse
import logging

# 确保 AOS 模块可导入
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("aos-review")


def main():
    parser = argparse.ArgumentParser(
        description="AOS 代码审查流水线 — 审查 → 修复 → 测试 → 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
组件组合:
  LLM 推理 (云端/本地) + SandboxManager + WorkspaceManager + ThreadPoolExecutor
  = 一个命令完成完整代码审查闭环

示例:
  python scripts/aos_review.py src/
  python scripts/aos_review.py src/ --auto-fix --output report.md
        """,
    )
    parser.add_argument("target", help="目标目录路径")
    parser.add_argument("--no-parallel", action="store_true", help="禁用并行审查")
    parser.add_argument("--auto-fix", action="store_true", help="自动修复（仅安全修复）")
    parser.add_argument("--no-tests", action="store_true", help="跳过测试执行")
    parser.add_argument("--output", "-o", default=None, help="报告输出路径 (默认: 打印到终端)")
    parser.add_argument(
        "--model", default="auto",
        choices=["auto", "deeproute", "zhipu", "local", "ollama"],
        help="模型选择 (默认: auto 自动检测)",
    )
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    target_dir = os.path.abspath(args.target)
    if not os.path.isdir(target_dir):
        print(f"错误: 目录不存在: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AOS 代码审查流水线")
    print(f"  目标: {target_dir}")
    print(f"  模型: {args.model}")
    print(f"  模式: {'串行' if args.no_parallel else '并行'} | {'自动修复' if args.auto_fix else '仅审查'} | {'运行测试' if not args.no_tests else '跳过测试'}")
    print(f"{'='*60}\n")

    from capabilities.code_review import CodeReviewPipeline

    pipeline = CodeReviewPipeline(model_provider=args.model)
    logger.info("使用模型: %s", pipeline._model_used)

    print(f"  模型状态: {pipeline._model_used}")
    print(f"  正在扫描...")

    report = pipeline.run(
        target_dir=target_dir,
        parallel=not args.no_parallel,
        auto_fix=args.auto_fix,
        run_tests=not args.no_tests,
    )

    # 生成报告
    report_text = pipeline.generate_report(report, output_path=args.output)

    if args.output:
        print(f"\n  报告已保存: {args.output}")
    else:
        print(f"\n{report_text}")

    # 简要总结
    print(f"\n{'='*60}")
    print(f"  审查完成!")
    print(f"  文件: {report.files_scanned} 扫描 / {report.files_reviewed} 审查")
    print(f"  问题: {report.total_issues} 个 (C:{report.critical_issues} H:{report.high_issues} M:{report.medium_issues} L:{report.low_issues})")
    print(f"  模型: {report.model_used}")
    print(f"  耗时: {report.duration_seconds}s")
    if report.errors:
        print(f"  错误: {len(report.errors)} 个")
    print(f"{'='*60}\n")

    # 退出码：有严重问题返回 1
    if report.critical_issues > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()