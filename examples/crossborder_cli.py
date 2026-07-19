"""跨境合规智能体 CLI 入口。

用法：
    python examples/crossborder_cli.py --demo
    python examples/crossborder_cli.py --product "蓝牙耳机，含锂电池" --dest DE --channel amazon
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from skills.crossborder_compliance import CrossBorderAgent  # noqa: E402


DEMO_CASES = [
    {
        "name": "蓝牙耳机 → 德国 Amazon",
        "context": {
            "product": "TWS蓝牙耳机，含锂电池，2.4GHz无线，售价29.99欧元",
            "destination": "DE",
            "channel": "amazon",
            "existing_certs": ["CE"],
        },
    },
    {
        "name": "儿童玩具 → 美国",
        "context": {
            "product": "儿童积木玩具，适合3岁以上，塑料材质，售价19.99美元",
            "destination": "US",
            "channel": "amazon",
            "existing_certs": [],
        },
    },
    {
        "name": "LED灯带 → 日本",
        "context": {
            "product": "RGB LED灯带，5米，含遥控器和电源适配器，售价3980日元",
            "destination": "JP",
            "channel": "shopify",
            "existing_certs": [],
        },
    },
]


def main():
    parser = argparse.ArgumentParser(description="AOS 跨境合规智能体")
    parser.add_argument("--product", help="商品描述")
    parser.add_argument("--dest", help="目的国代码（DE/US/UK/JP/AU）")
    parser.add_argument("--channel", default="", help="销售渠道")
    parser.add_argument("--certs", default="", help="已有认证，逗号分隔")
    parser.add_argument("--demo", action="store_true", help="运行内置演示案例")
    parser.add_argument("--output", "-o", help="输出报告路径")
    args = parser.parse_args()

    agent = CrossBorderAgent()

    if args.demo:
        for case in DEMO_CASES:
            print(f"\n{'='*60}")
            print(f"  案例：{case['name']}")
            print(f"{'='*60}")
            result = agent.execute(case["context"])
            report = format_report(result)
            print(report)
    elif args.product and args.dest:
        context = {
            "product": args.product,
            "destination": args.dest,
            "channel": args.channel,
            "existing_certs": [c.strip() for c in args.certs.split(",") if c.strip()],
        }
        result = agent.execute(context)
        report = format_report(result)
        if args.output:
            Path(args.output).write_text(report, encoding="utf-8")
            print(f"报告已保存: {args.output}")
        else:
            print(report)
    else:
        parser.print_help()
        sys.exit(1)


def format_report(result: dict) -> str:
    if not result["ok"]:
        return f"❌ 分析失败: {result.get('error')}"

    lines = []
    lines.append(f"\n📦 商品：{result['product']}")
    lines.append(f"🌍 目的国：{result['destination']}")
    lines.append(f"🏷️ 品类识别：{', '.join(result['categories'])}")

    # 风险等级
    risk = result["risk_level"]
    risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢", "COMPLIANT": "✅"}.get(risk, "❓")
    lines.append(f"\n{risk_emoji} 风险等级：{risk}")

    # 合规要求
    lines.append(f"\n📋 适用合规要求（{len(result['requirements'])} 项）：")
    for r in result["requirements"]:
        sev_mark = {"mandatory": "❗", "recommended": "💡", "conditional": "❓"}.get(r["severity"], "")
        lines.append(f"   {sev_mark} [{r['id']}] {r['requirement']} ({r['category']})")

    # 缺口
    if result["gaps"]:
        lines.append(f"\n❌ 合规缺口（{len(result['gaps'])} 项未满足）：")
        for g in result["gaps"]:
            lines.append(f"   - [{g['id']}] {g['requirement']} | 费用: {g['cost']} | 周期: {g['timeline']}")
    else:
        lines.append("\n✅ 无合规缺口，已满足所有强制要求")

    # 行动计划
    if result["action_plan"]:
        lines.append(f"\n📝 行动计划：")
        for a in result["action_plan"]:
            if a["severity"] == "info":
                lines.append(f"   {a['action']}")
            else:
                lines.append(f"   {a['priority']}. {a['action']} [{a['category']}] "
                             f"费用:{a['cost']} 周期:{a['timeline']}")

    # 估算
    lines.append(f"\n💰 费用估算：{result['cost_estimate']}")
    lines.append(f"⏱ 周期估算：{result['timeline_estimate']}")

    # trace
    t = result["trace"]
    lines.append(f"\n{'─'*60}")
    lines.append(f"⏱ 耗时 {t['elapsed_sec']}s | 步骤 {len(t['steps'])} | 全链路可复核 ✓")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
