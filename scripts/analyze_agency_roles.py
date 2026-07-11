#!/usr/bin/env python3
"""Agency Roles 收口可行性分析器（只读，不修改任何文件）。

目的：把「272 个角色文件怎么收口」从拍脑袋变成可量化数据。
- 统计 get_brain() 调用分布
- 把每个角色文件里 brain.<method> 的用法归类到「可经 _kernel_bridge 薄壳吸收」
  或「需要额外处理」
- 输出可机读的 JSON 摘要，供 Layer 2 灰度脚本使用

用法：
    python scripts/analyze_agency_roles.py
    python scripts/analyze_agency_roles.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROLES_DIR = Path(__file__).resolve().parent.parent / "src" / "skills" / "agency_roles"
SKIP = {"__init__.py", "_kernel_bridge.py"}

# 薄壳（_kernel_bridge._KernelRuntime）能吸收的 brain 用法
MAPPABLE = {
    "chat": "rt.chat",
    "call_skill": "rt.call_skill",
    "hermes.execute_skill": "rt.call_skill",
    "hermes.chat": "rt.chat",
}

assign_re = re.compile(r"(\w+)\s*=\s*get_brain\s*\(")
call_re = re.compile(r"\b(\w+)\.([\w.]+)\s*\(")
name_re = re.compile(r'^NAME\s*=\s*["\']([^"\']+)["\']', re.M)
import_re = re.compile(r"from\s+core\s+import\s+get_brain|import\s+get_brain|from\s+core\s+import\s+\w*,\s*get_brain")


def analyze_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    assigns = assign_re.findall(text)
    var = assigns[0] if assigns else "brain"
    methods = []
    for m in call_re.finditer(text):
        if m.group(1) == var:
            methods.append(m.group(2))
    # 也捕获 hermes.execute_skill 这类带点的
    used = sorted(set(methods))
    mappable_methods = {m for m in used if m in MAPPABLE or m.split(".")[0] == "hermes"}
    unmappable = [m for m in used if m not in MAPPABLE and m.split(".")[0] != "hermes"]
    nm = name_re.search(text)
    return {
        "file": path.name,
        "role_id": nm.group(1) if nm else None,
        "get_brain_calls": text.count("get_brain("),
        "imports_get_brain": bool(import_re.search(text)),
        "brain_var": var,
        "methods_used": used,
        "mappable": not unmappable,
        "unmappable_methods": unmappable,
        "fully_mappable": (not unmappable) and bool(used),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="写出 JSON 摘要路径")
    args = ap.parse_args()

    files = sorted(p for p in ROLES_DIR.glob("*.py") if p.name not in SKIP)
    rows = [analyze_file(p) for p in files]

    total = len(rows)
    with_gb = [r for r in rows if r["get_brain_calls"] > 0]
    fully = [r for r in rows if r["fully_mappable"]]
    partial = [r for r in rows if r["get_brain_calls"] > 0 and not r["fully_mappable"]]
    gb_calls = sum(r["get_brain_calls"] for r in rows)

    # 汇总 brain 方法使用频次
    method_hist: dict[str, int] = {}
    for r in rows:
        for m in r["methods_used"]:
            method_hist[m] = method_hist.get(m, 0) + 1

    summary = {
        "roles_dir": str(ROLES_DIR),
        "files_total": total,
        "files_with_get_brain": len(with_gb),
        "get_brain_calls_total": gb_calls,
        "fully_mappable_files": len(fully),
        "partial_files": len(partial),
        "method_histogram": dict(sorted(method_hist.items(), key=lambda x: -x[1])),
        "partial_samples": [
            {"file": r["file"], "role_id": r["role_id"],
             "unmappable": r["unmappable_methods"], "methods": r["methods_used"]}
            for r in partial[:25]
        ],
    }

    print(f"角色文件总数          : {total}")
    print(f"含 get_brain 的文件    : {len(with_gb)}")
    print(f"get_brain() 调用总数   : {gb_calls}")
    print(f"完全可薄壳收口的文件   : {len(fully)}  ({100*len(fully)/max(total,1):.0f}%)")
    print(f"需额外处理的文件       : {len(partial)}")
    print("--- brain 方法使用频次 ---")
    for m, c in summary["method_histogram"].items():
        tag = "可收口" if (m in MAPPABLE or m.split('.')[0] == 'hermes') else "⚠ 需处理"
        print(f"  {m:28s} {c:4d}  {tag}")
    print("--- 需额外处理样本（前 25）---")
    for s in summary["partial_samples"]:
        print(f"  {s['file']:30s} unmappable={s['unmappable']}")

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"summary": summary, "files": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 摘要已写出: {args.json}")


if __name__ == "__main__":
    main()
