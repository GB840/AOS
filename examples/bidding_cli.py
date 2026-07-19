"""投标分析智能体 CLI 入口。

用法：
    python examples/bidding_cli.py <招标文件.pdf> [--company company.json]

示例：
    python examples/bidding_cli.py 某项目招标文件.pdf
    python examples/bidding_cli.py 某项目招标文件.pdf --company my_company.json
    python examples/bidding_cli.py --demo   # 用内置模拟招标文件演示
"""
import argparse
import json
import sys
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Windows 终端 GBK 编码修复
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from skills.bidding_agent import BiddingAgent  # noqa: E402


def generate_demo_pdf(output_path: str) -> str:
    """生成一份模拟招标文件 PDF（用于演示/测试）。"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    except ImportError:
        print("需要 reportlab: pip install reportlab")
        sys.exit(1)

    # 尝试注册中文字体
    font_name = "Helvetica"
    for fp in [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simsun.ttc",
    ]:
        if Path(fp).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJK", fp))
                font_name = "CJK"
                break
            except Exception:
                continue

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    style = ParagraphStyle("body", parent=styles["Normal"],
                           fontName=font_name, fontSize=11, leading=18)
    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 fontName=font_name, fontSize=16)

    content = [
        Paragraph("XX市智慧城市信息化建设项目", title_style),
        Paragraph("招标文件", title_style),
        Spacer(1, 20),
        Paragraph("第一章 招标公告", style),
        Spacer(1, 10),
        Paragraph("项目编号：ZC-2026-0718", style),
        Paragraph("投标截止时间：2026年08月15日 09:30", style),
        Paragraph("开标时间：2026年08月15日 10:00", style),
        Paragraph("投标保证金：人民币5万元整", style),
        Paragraph("最高限价：人民币380万元", style),
        Spacer(1, 15),
        Paragraph("第二章 投标人资格要求", style),
        Spacer(1, 10),
        Paragraph("1. 投标人须具备有效的营业执照。", style),
        Paragraph("2. 投标人须具备计算机信息系统集成及服务资质二级及以上。", style),
        Paragraph("3. 投标人须具备ISO 9001质量管理体系认证。", style),
        Paragraph("4. 投标人近3年（2023年至今）须具有不少于2个单项合同金额不低于200万元的类似项目业绩。", style),
        Paragraph("5. 项目经理须持有PMP或信息系统项目管理师证书。", style),
        Paragraph("6. 投标人须具备有效的安全生产许可证。", style),
        Spacer(1, 15),
        Paragraph("第三章 技术要求", style),
        Spacer(1, 10),
        Paragraph("1. 系统须满足GB/T 22239-2019信息安全技术网络安全等级保护三级要求。", style),
        Paragraph("2. 系统响应时间不超过2秒，并发用户支持不少于500人。", style),
        Paragraph("3. 须提供7x24小时运维保障，故障响应时间不超过30分钟。", style),
        Paragraph("4. 数据存储须支持国产化数据库（达梦/人大金仓）。", style),
        Spacer(1, 15),
        Paragraph("第四章 商务要求", style),
        Spacer(1, 10),
        Paragraph("工期：合同签订后180个日历天内完成全部建设内容。", style),
        Paragraph("质保期：验收合格后不少于3年。", style),
        Paragraph("付款方式：合同签订后支付30%，中期验收支付40%，终验后支付30%。", style),
        Spacer(1, 15),
        Paragraph("第五章 投标文件要求", style),
        Spacer(1, 10),
        Paragraph("1. 投标文件正本1份，副本4份，电子版U盘1份。", style),
        Paragraph("2. 投标文件须密封，封口处加盖投标人公章及法人章。", style),
        Paragraph("3. 投标文件须编制目录和连续页码。", style),
        Paragraph("4. 所有实质性条款（★标记）必须逐条响应，不得偏离。", style),
        Paragraph("5. 报价为唯一报价，不接受选择性报价或备选方案。", style),
        Paragraph("6. 投标报价不得超过最高限价380万元，大小写金额须一致。", style),
        Spacer(1, 15),
        Paragraph("第六章 评标办法", style),
        Spacer(1, 10),
        Paragraph("本项目采用综合评分法，技术分60分，商务分30分，价格分10分。", style),
        Paragraph("★实质性条款未响应的，作无效投标处理。", style),
    ]

    doc.build(content)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="AOS 投标分析智能体")
    parser.add_argument("pdf", nargs="?", help="招标文件 PDF 路径")
    parser.add_argument("--company", help="企业资质 JSON 文件路径")
    parser.add_argument("--demo", action="store_true", help="生成模拟招标文件并演示")
    parser.add_argument("--output", "-o", help="输出报告路径（默认打印到终端）")
    args = parser.parse_args()

    if args.demo:
        demo_path = str(Path(__file__).parent / "demo_bidding_doc.pdf")
        print(f"生成模拟招标文件: {demo_path}")
        generate_demo_pdf(demo_path)
        args.pdf = demo_path
        # 模拟企业信息
        company = {
            "name": "XX科技有限公司",
            "qualifications": [
                "计算机信息系统集成及服务资质二级",
                "ISO 9001质量管理体系认证",
                "ISO 27001信息安全管理体系认证",
            ],
            "certificates": ["PMP", "信息系统项目管理师"],
            "past_projects": [
                "2024年某市政务云平台建设（合同额280万）",
                "2025年某区智慧社区项目（合同额350万）",
            ],
        }
    elif args.pdf:
        company = {}
        if args.company:
            company = json.loads(Path(args.company).read_text(encoding="utf-8"))
    else:
        parser.print_help()
        sys.exit(1)

    # 执行分析
    agent = BiddingAgent()
    result = agent.execute({"pdf_path": args.pdf, "company_profile": company})

    if not result["ok"]:
        print(f"\n❌ 分析失败: {result.get('error')}")
        sys.exit(1)

    # 输出报告
    report = format_report(result)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\n报告已保存: {args.output}")
    else:
        print(report)


def format_report(result: dict) -> str:
    """将分析结果格式化为可读报告。"""
    lines = []
    lines.append("=" * 60)
    lines.append("        投标文件智能分析报告")
    lines.append("=" * 60)

    # 基本信息
    a = result["analysis"]
    lines.append(f"\n📄 文件概况：{a['pdf_pages']} 页 | "
                 f"{a['sections_detected']} 个章节 | "
                 f"{a['tables_hint']} 个疑似表格")

    if a["key_info"]:
        lines.append("\n📌 关键信息：")
        for kw in a["key_info"]:
            lines.append(f"   {kw}")

    # 需求提取
    lines.append(f"\n📋 招标需求（提取 {len(a['requirements'])} 条）：")
    for req in a["requirements"]:
        lines.append(f"   [{req['type']}] {req['detail'][:100]}")

    # 合规风险
    lines.append(f"\n🔍 合规检查（{len(result['compliance'])} 条规则）：")
    criticals = result.get("critical_risks", [])
    if criticals:
        lines.append(f"   ⚠️ 关键风险 {len(criticals)} 项：")
        for c in criticals:
            lines.append(f"      [{c['rule_id']}] {c['description']} — {c['risk_note']}")
    else:
        lines.append("   ✅ 未发现关键合规风险")

    # 资质匹配
    qm = result.get("qualification_match", {})
    if qm:
        lines.append(f"\n🏢 资质匹配：满足 {qm['matched']} 项 | "
                     f"缺口 {qm['missing']} 项 | 待确认 {qm['uncertain']} 项")
        if qm.get("missing_items"):
            lines.append("   ❌ 缺口项：")
            for item in qm["missing_items"]:
                lines.append(f"      - {item['detail'][:80]}")

    # 策略建议
    lines.append(f"\n💡 投标策略建议：")
    lines.append(result["strategy"])

    # trace
    t = result["trace"]
    lines.append(f"\n{'─' * 60}")
    lines.append(f"⏱ 耗时 {t['elapsed_sec']}s | "
                 f"步骤 {len(t['steps'])} | "
                 f"全链路可复核 ✓")
    lines.append("=" * 60)

    return "\n".join(lines)


if __name__ == "__main__":
    main()
