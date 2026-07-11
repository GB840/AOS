#!/usr/bin/env python
"""
aos-analyze — AOS 文档/数据分析流水线

用法:
    python scripts/aos_analyze.py <target_dir> [options]

示例:
    python scripts/aos_analyze.py docs/                       # 分析 docs/ 目录
    python scripts/aos_analyze.py src/ --no-parallel           # 串行分析
    python scripts/aos_analyze.py . --output reports/analysis.md  # 分析当前目录

组件组合:
    LLM 推理 (云端/本地) + WorkspaceManager + 文件分类器 + ThreadPoolExecutor
    = 一个命令完成完整文档分析闭环

与代码审查的区别:
    code_review → 审代码质量，找 bug/安全/风格问题
    doc_analysis → 分析文档结构，提取关键信息，评估可读性
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
logger = logging.getLogger("aos-analyze")


def main():
    parser = argparse.ArgumentParser(
        description="AOS 文档/数据分析流水线 — 分析 → 提取 → 洞察 → 报告",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
组件组合:
  LLM 推理 + WorkspaceManager + 文件分类器 + ThreadPoolExecutor
  = 一个命令完成完整文档分析闭环

与代码审查的区别:
  code_review → 审代码质量，找 bug/安全/风格问题
  doc_analysis → 分析文档结构，提取关键信息，评估可读性

示例:
  python scripts/aos_analyze.py docs/
  python scripts/aos_analyze.py src/ --output reports/analysis.md
        """,
    )
    parser.add_argument("target", help="目标目录路径")
    parser.add_argument("--no-parallel", action="store_true", help="禁用并行分析")
    parser.add_argument("--output", "-o", default=None, help="报告输出路径")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    target_dir = os.path.abspath(args.target)
    if not os.path.isdir(target_dir):
        print(f"错误: 目录不存在: {target_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  AOS 文档/数据分析流水线")
    print(f"  目标: {target_dir}")
    print(f"  模式: {'串行' if args.no_parallel else '并行'}")
    print(f"{'='*60}\n")

    from capabilities.doc_analysis import DocAnalysisPipeline

    pipeline = DocAnalysisPipeline()
    logger.info("使用模型: %s", pipeline._model_used)

    print(f"  模型状态: {pipeline._model_used}")
    print(f"  正在扫描...")

    report = pipeline.run(target_dir=target_dir, parallel=not args.no_parallel)

    report_text = pipeline.generate_report(report, output_path=args.output)

    if args.output:
        print(f"\n  报告已保存: {args.output}")
    else:
        print(f"\n{report_text}")

    print(f"\n{'='*60}")
    print(f"  分析完成!")
    print(f"  文件: {report.files_scanned} 扫描 / {report.files_analyzed} 分析")
    print(f"  洞察: {report.total_insights} 个")
    print(f"  模型: {report.model_used}")
    print(f"  耗时: {report.duration_seconds}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()