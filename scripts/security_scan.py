#!/usr/bin/env python
"""
AOS 安全扫描脚本

一键运行所有安全扫描工具，生成综合报告。

使用方法:
    python scripts/security_scan.py

扫描工具:
    - Bandit: Python代码静态分析
    - Safety: 依赖漏洞扫描
    - Ruff: 代码质量和安全检查
    - MyPy: 类型检查
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class SecurityScanner:
    """安全扫描器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: Dict[str, Dict] = {}
        self.start_time = datetime.now()

    def run_command(self, cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
        """运行命令并返回结果"""
        print(f"运行: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=cwd or self.project_root,
            capture_output=True,
            text=True,
            timeout=300
        )
        return result.returncode, result.stdout, result.stderr

    def scan_bandit(self) -> None:
        """运行Bandit扫描"""
        print("\n" + "="*60)
        print("运行 Bandit 扫描...")
        print("="*60)

        returncode, stdout, stderr = self.run_command([
            sys.executable, "-m", "bandit",
            "-r", "src/",
            "-f", "json",
            "-o", "bandit-report.json"
        ])

        # 同时输出可读格式
        _, stdout_human, _ = self.run_command([
            sys.executable, "-m", "bandit",
            "-r", "src/"
        ])
        print(stdout_human)

        self.results["bandit"] = {
            "success": returncode == 0,
            "output": stdout,
            "error": stderr,
            "report_file": "bandit-report.json"
        }

    def scan_safety(self) -> None:
        """运行Safety扫描"""
        print("\n" + "="*60)
        print("运行 Safety 扫描...")
        print("="*60)

        returncode, stdout, stderr = self.run_command([
            sys.executable, "-m", "safety",
            "check",
            "--json",
            "--output", "safety-report.json"
        ])

        # 同时输出可读格式
        _, stdout_human, _ = self.run_command([
            sys.executable, "-m", "safety",
            "check"
        ])
        print(stdout_human)

        self.results["safety"] = {
            "success": returncode == 0,
            "output": stdout,
            "error": stderr,
            "report_file": "safety-report.json"
        }

    def scan_ruff(self) -> None:
        """运行Ruff扫描"""
        print("\n" + "="*60)
        print("运行 Ruff 扫描...")
        print("="*60)

        returncode, stdout, stderr = self.run_command([
            sys.executable, "-m", "ruff",
            "check", "src/", "tests/"
        ])
        print(stdout)

        self.results["ruff"] = {
            "success": returncode == 0,
            "output": stdout,
            "error": stderr
        }

    def scan_mypy(self) -> None:
        """运行MyPy扫描"""
        print("\n" + "="*60)
        print("运行 MyPy 扫描...")
        print("="*60)

        returncode, stdout, stderr = self.run_command([
            sys.executable, "-m", "mypy",
            "src/",
            "--ignore-missing-imports"
        ])
        print(stdout)

        self.results["mypy"] = {
            "success": returncode == 0,
            "output": stdout,
            "error": stderr
        }

    def generate_report(self) -> None:
        """生成综合报告"""
        print("\n" + "="*60)
        print("生成综合报告...")
        print("="*60)

        report = {
            "scan_time": self.start_time.isoformat(),
            "project_root": str(self.project_root),
            "results": self.results,
            "summary": {
                "total_scans": len(self.results),
                "passed_scans": sum(1 for r in self.results.values() if r["success"]),
                "failed_scans": sum(1 for r in self.results.values() if not r["success"])
            }
        }

        # 保存JSON报告
        report_file = self.project_root / "security-scan-report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 生成Markdown报告
        md_report = self._generate_markdown_report(report)
        md_file = self.project_root / "security-scan-report.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_report)

        print(f"\n报告已生成:")
        print(f"  - JSON: {report_file}")
        print(f"  - Markdown: {md_file}")

        # 打印摘要
        self._print_summary(report)

    def _generate_markdown_report(self, report: Dict) -> str:
        """生成Markdown报告"""
        md = []
        md.append("# AOS 安全扫描报告")
        md.append(f"\n**扫描时间**: {report['scan_time']}")
        md.append(f"**项目根目录**: {report['project_root']}")
        md.append("\n## 扫描摘要")
        md.append(f"\n| 工具 | 状态 |")
        md.append(f"|------|------|")
        
        for tool, result in report["results"].items():
            status = "✅ 通过" if result["success"] else "❌ 失败"
            md.append(f"| {tool} | {status} |")

        md.append(f"\n**总计**: {report['summary']['total_scans']} 个扫描")
        md.append(f"**通过**: {report['summary']['passed_scans']} 个")
        md.append(f"**失败**: {report['summary']['failed_scans']} 个")

        md.append("\n## 详细结果")

        for tool, result in report["results"].items():
            md.append(f"\n### {tool}")
            md.append(f"\n**状态**: {'✅ 通过' if result['success'] else '❌ 失败'}")
            
            if result.get("output"):
                md.append("\n**输出**:")
                md.append("```")
                md.append(result["output"])
                md.append("```")
            
            if result.get("error"):
                md.append("\n**错误**:")
                md.append("```")
                md.append(result["error"])
                md.append("```")
            
            if result.get("report_file"):
                md.append(f"\n**报告文件**: {result['report_file']}")

        md.append("\n## 建议")
        md.append("\n1. 修复所有失败的安全问题")
        md.append("2. 定期运行安全扫描（建议每周一次）")
        md.append("3. 在CI/CD中集成安全扫描")
        md.append("4. 关注依赖漏洞公告，及时更新依赖")
        md.append("5. 加强代码审查，防止引入新的安全问题")

        return "\n".join(md)

    def _print_summary(self, report: Dict) -> None:
        """打印摘要"""
        print("\n" + "="*60)
        print("扫描摘要")
        print("="*60)
        print(f"总计: {report['summary']['total_scans']} 个扫描")
        print(f"通过: {report['summary']['passed_scans']} 个")
        print(f"失败: {report['summary']['failed_scans']} 个")
        print("\n详细结果:")
        for tool, result in report["results"].items():
            status = "✅" if result["success"] else "❌"
            print(f"  {status} {tool}")

    def run_all(self) -> None:
        """运行所有扫描"""
        print("AOS 安全扫描")
        print(f"项目根目录: {self.project_root}")
        print(f"开始时间: {self.start_time.isoformat()}")

        # 检查工具是否安装
        self._check_tools()

        # 运行扫描
        self.scan_bandit()
        self.scan_safety()
        self.scan_ruff()
        self.scan_mypy()

        # 生成报告
        self.generate_report()

        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        print(f"\n扫描完成! 耗时: {duration:.2f}秒")

    def _check_tools(self) -> None:
        """检查工具是否安装"""
        print("\n检查工具...")
        tools = ["bandit", "safety", "ruff", "mypy"]
        missing = []

        for tool in tools:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", tool, "--version"],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode == 0:
                    print(f"  ✅ {tool}")
                else:
                    print(f"  ❌ {tool} (未正确安装)")
                    missing.append(tool)
            except Exception:
                print(f"  ❌ {tool} (未安装)")
                missing.append(tool)

        if missing:
            print(f"\n缺少工具: {', '.join(missing)}")
            print("请运行: pip install bandit safety ruff mypy")
            sys.exit(1)


def main():
    """主函数"""
    project_root = Path(__file__).parent.parent
    scanner = SecurityScanner(project_root)
    scanner.run_all()


if __name__ == "__main__":
    main()