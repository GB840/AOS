#!/usr/bin/env python
"""
aos-debate — AOS 多专家协作讨论

用法:
    python scripts/aos_debate.py "你的问题" [options]

示例:
    python scripts/aos_debate.py "设计一个支持100万用户的实时聊天系统"
    python scripts/aos_debate.py "如何重构一个遗留的单体应用" --roles architect,developer,devops
    python scripts/aos_debate.py "产品应该先做iOS还是Android" --roles product,developer,architect
    python scripts/aos_debate.py "..." --no-llm --output reports/debate.md

组件组合:
    7个内置角色 + LLM + 模板引擎 + 综合器
    = 一个团队讨论一个问题，产出结构化报告

三种 Demo 对比:
    code_review  → 审代码（单视角，多文件）
    doc_analysis → 读文档（单视角，多文件）
    agent_collab → 团队讨论（多视角，单任务）
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
logger = logging.getLogger("aos-debate")

AVAILABLE_ROLES = ["architect", "developer", "security", "product", "devops", "data", "reviewer"]


def main():
    parser = argparse.ArgumentParser(
        description="AOS 多专家协作讨论 — 一个团队讨论一个问题",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
组件组合:
  7个内置角色 + LLM + 模板引擎 + 综合器
  = 一个团队讨论一个问题，产出结构化报告

可用角色: architect, developer, security, product, devops, data, reviewer

示例:
  python scripts/aos_debate.py "设计一个支持100万用户的实时聊天系统"
  python scripts/aos_debate.py "如何重构遗留单体应用" --roles architect,developer,devops
  python scripts/aos_debate.py "..." --no-llm --output reports/debate.md
        """,
    )
    parser.add_argument("task", help="需要讨论的问题")
    parser.add_argument(
        "--roles", "-r", default="architect,developer,security,product",
        help=f"参与讨论的角色，逗号分隔。可用: {', '.join(AVAILABLE_ROLES)}",
    )
    parser.add_argument("--no-llm", action="store_true", help="使用模板模式（不调用 LLM）")
    parser.add_argument("--output", "-o", default=None, help="报告输出路径")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式")

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    roles = [r.strip() for r in args.roles.split(",") if r.strip() in AVAILABLE_ROLES]
    if not roles:
        roles = ["architect", "developer", "security", "product"]

    print(f"\n{'='*60}")
    print(f"  AOS 多专家协作讨论")
    print(f"  问题: {args.task[:60]}{'...' if len(args.task) > 60 else ''}")
    print(f"  专家: {', '.join(roles)} ({len(roles)}人)")
    print(f"  模式: {'模板' if args.no_llm else 'LLM'}")
    print(f"{'='*60}\n")

    from capabilities.agent_collab import AgentCollaboration

    engine = AgentCollaboration()
    logger.info("使用模型: %s", engine._model_used)

    print(f"  模型状态: {engine._model_used}")
    print(f"  正在讨论...")

    result = engine.debate(task=args.task, roles=roles, use_llm=not args.no_llm)

    report_text = engine.generate_report(result, output_path=args.output)

    if args.output:
        print(f"\n  报告已保存: {args.output}")
    else:
        print(f"\n{report_text}")

    print(f"\n{'='*60}")
    print(f"  讨论完成!")
    print(f"  专家: {len(result.opinions)} 位发言")
    print(f"  共识: {len(result.consensus)} 项")
    print(f"  分歧: {len(result.disagreements)} 项")
    print(f"  模型: {result.model_used}")
    print(f"  耗时: {result.duration_seconds}s")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()