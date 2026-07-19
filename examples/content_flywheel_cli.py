"""内容飞轮 CLI — 直接调用 kernel.plugins.content_flywheel 引擎。

用法：
    python examples/content_flywheel_cli.py --demo
    python examples/content_flywheel_cli.py --topic "AI 智能体" --cycles 5
"""
from __future__ import annotations

import argparse
import os
import sys

# Windows 控制台 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def run_flywheel(topic: str, cycles: int, platforms: list, style: str) -> dict:
    """直接构建引擎实例并跑循环。"""
    from kernel.plugins.content_flywheel import ContentFlywheel

    config = {
        "max_cycles": cycles,
        "interval_seconds": 0,
        "platforms": platforms,
        "style": style,
        "duration": 60,
        "auto_publish": False,
    }
    # route_fn=None → 各阶段返回 ok=False，但反思闭环仍正常运转
    fw = ContentFlywheel(topic=topic, route_fn=None, config=config)
    results = []
    for _ in range(cycles):
        results.append(fw.run_once())
    return {"topic": topic, "cycles": results, "state": fw.get_state()}


def format_report(data: dict) -> str:
    parts = [
        "=" * 60,
        "        内容飞轮执行报告",
        "=" * 60,
        "",
        f"主题：{data['topic']}",
        "",
    ]
    for cycle in data["cycles"]:
        num = cycle.get("cycle_num", "?")
        status = cycle.get("status", "?")
        icon = {"completed": "✅", "partial": "⚠️", "failed": "❌"}.get(status, "❓")
        parts.append(f"  {icon} 第 {num} 轮 [{status}]")
        for stage_name in ["forge", "cast", "echo", "refine"]:
            sd = cycle.get("stages", {}).get(stage_name, {})
            if isinstance(sd, dict):
                ok = sd.get("ok", False)
                parts.append(f"     {'✓' if ok else '✗'} {stage_name}"
                             f"{'' if ok else ' — ' + sd.get('error', '')[:50]}")
        parts.append("")

    parts.extend(["─" * 60, "=" * 60])
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="AOS 内容飞轮 CLI")
    parser.add_argument("--topic", type=str, default="AI 智能体", help="内容主题")
    parser.add_argument("--cycles", type=int, default=3, help="循环次数")
    parser.add_argument("--platforms", type=str, default="douyin,xiaohongshu",
                        help="分发平台（逗号分隔）")
    parser.add_argument("--style", type=str, default="douyin", help="内容风格")
    parser.add_argument("--demo", action="store_true", help="运行内置演示")
    args = parser.parse_args()

    if args.demo:
        demos = [
            ("AI 智能体", 3, ["douyin", "xiaohongshu"], "douyin"),
            ("跨境电商合规", 2, ["bilibili"], "knowledge"),
            ("Python 自动化办公", 4, ["douyin", "bilibili", "xiaohongshu"], "tutorial"),
        ]
        for i, (topic, cycles, platforms, style) in enumerate(demos, 1):
            print(f"\n  演示 {i}/{len(demos)}：{topic}\n")
            data = run_flywheel(topic, cycles, platforms, style)
            print(format_report(data))
    else:
        platforms = [p.strip() for p in args.platforms.split(",")]
        data = run_flywheel(args.topic, args.cycles, platforms, args.style)
        print(format_report(data))

    # 显示教训库状态
    from kernel.plugins.content_flywheel import _LESSONS_PATH
    if os.path.exists(_LESSONS_PATH):
        with open(_LESSONS_PATH, encoding="utf-8") as f:
            count = sum(1 for l in f if l.strip())
        print(f"\n📁 教训库：{_LESSONS_PATH} ({count} 条)")
    else:
        print("\n📁 教训库：尚未创建（全成功时不写教训）")


if __name__ == "__main__":
    main()
