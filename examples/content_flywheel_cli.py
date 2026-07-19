"""内容飞轮 CLI 演示 — 无需外部引擎即可跑通完整闭环。

用法：
    python examples/content_flywheel_cli.py --demo
    python examples/content_flywheel_cli.py --topic "AI 智能体" --cycles 5
"""
from __future__ import annotations

import argparse
import sys
import os

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 确保 src/ 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    parser = argparse.ArgumentParser(description="AOS 内容飞轮 CLI")
    parser.add_argument("--topic", type=str, default="AI 智能体", help="内容主题")
    parser.add_argument("--cycles", type=int, default=3, help="循环次数")
    parser.add_argument("--platforms", type=str, default="douyin,xiaohongshu",
                        help="分发平台（逗号分隔）")
    parser.add_argument("--style", type=str, default="douyin", help="内容风格")
    parser.add_argument("--demo", action="store_true", help="运行内置演示")
    args = parser.parse_args()

    from skills.content_flywheel_skill import ContentFlywheelSkill

    skill = ContentFlywheelSkill()

    if args.demo:
        # 内置演示：跑 3 个不同主题
        demos = [
            {"topic": "AI 智能体", "max_cycles": 3, "platforms": ["douyin", "xiaohongshu"], "style": "douyin"},
            {"topic": "跨境电商合规", "max_cycles": 2, "platforms": ["bilibili"], "style": "knowledge"},
            {"topic": "Python 自动化办公", "max_cycles": 4, "platforms": ["douyin", "bilibili", "xiaohongshu"], "style": "tutorial"},
        ]
        for i, ctx in enumerate(demos, 1):
            print(f"\n{'='*60}")
            print(f"  演示 {i}/{len(demos)}：{ctx['topic']}")
            print(f"{'='*60}")
            result = skill.execute(ctx)
            print(skill.format_report(result))
            print()
    else:
        context = {
            "topic": args.topic,
            "max_cycles": args.cycles,
            "platforms": [p.strip() for p in args.platforms.split(",")],
            "style": args.style,
        }
        result = skill.execute(context)
        print(skill.format_report(result))

    # 显示教训文件状态
    lessons_path = skill._lessons_path
    if lessons_path.exists():
        lines = lessons_path.read_text(encoding="utf-8").strip().split("\n")
        print(f"\n📁 教训库：{lessons_path} ({len(lines)} 条)")
    else:
        print("\n📁 教训库：尚未创建")


if __name__ == "__main__":
    main()
