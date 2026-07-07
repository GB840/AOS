"""
AOS 开源资产归位 — 发现 / 分类 / 生成 DeerFlow 注册清单 / 出文档。

用法:
  PYTHONPATH=. python scripts/catalog_assets.py            # 发现 + 分类 + 打印 + 写文档
  PYTHONPATH=. python scripts/catalog_assets.py --register # 额外尝试真实注册进 DeerFlow

不依赖真实 DeerFlow 即可跑（静态解析）；--register 时若 DeerFlow 可导入则真注册。
"""

import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
_ROOT = Path(__file__).resolve().parents[1]  # repo root
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "src"))  # 让 `utils` / `src.deerflow` 均可导入

from src.deerflow.aos_assets import build_catalog, to_deerflow_registrations, register_all


def render_placement_md(cat: dict) -> str:
    s = cat["summary"]
    lines = [
        "# AOS 开源资产归位目录 (Asset Placement Map)",
        "",
        "> 用户决策 (2026-07-08)：仓库内 agents/skills 均为开源可复用构件，",
        "> 归位到 DeerFlow 子智能体 / 技能 或 对应基建平面，不重造。",
        "",
        "## 统计",
        "",
        f"- 子智能体 (sub-agents): **{s['subagents']}** → DeerFlow 子智能体",
        f"- 领域技能 (skills): **{s['skills']}**",
        f"  - DeerFlow 技能: {s['deerflow_skills']}",
        f"  - Mem0 平面 (记忆/知识): {s['mem0_plane']}",
        f"  - browser-use 平面 (UI 自动化): {s['browser_use_plane']}",
        f"  - fabric 自举能力 (元技能): {s['fabric_capability']}",
        f"- 角色模板 (agency_roles): **{s['roles']}** → DeerFlow 子智能体角色模板",
        f"- DeerFlow 子智能体注册项合计: **{len(to_deerflow_registrations(cat))}**",
        "",
        "## 子智能体 → DeerFlow 子智能体",
        "",
        "| 名称 | 源码 | 说明 |",
        "|---|---|---|",
    ]
    for a in cat["subagents"]:
        lines.append(f"| `{a.name}` | `{a.source}` | {a.note} |")
    lines += ["", "## 角色模板 → DeerFlow 子智能体角色模板 (节选前 40)", "",
              "| 名称 | 源码 | 说明 |", "|---|---|---|"]
    for a in cat["roles"][:40]:
        lines.append(f"| `{a.name}` | `{a.source}` | {a.note} |")
    if len(cat["roles"]) > 40:
        lines.append(f"| … | … | 其余 {len(cat['roles']) - 40} 个角色同结构省略 |")
    lines += ["", "## 领域技能 → 按平面归位", ""]
    for target, assets in sorted(cat["skills_by_target"].items()):
        label = {
            "deerflow:skill": "DeerFlow 技能",
            "plane:mem0": "Mem0 平面 (记忆/知识)",
            "plane:browser-use": "browser-use 平面 (UI 自动化)",
            "fabric:capability": "fabric 自举能力 (元技能)",
        }.get(target, target)
        lines.append(f"### {label} ({len(assets)})")
        lines.append("")
        lines.append("| 名称 | 源码 | 说明 |")
        lines.append("|---|---|---|")
        for a in assets:
            lines.append(f"| `{a.name}` | `{a.source}` | {a.note} |")
        lines.append("")
    return "\n".join(lines)


def main():
    do_register = "--register" in sys.argv[1:]
    cat = build_catalog()
    s = cat["summary"]

    print("=" * 64)
    print("AOS 开源资产归位目录")
    print("=" * 64)
    print(f"  子智能体       : {s['subagents']}  → DeerFlow 子智能体")
    print(f"  领域技能       : {s['skills']}")
    print(f"    ├ DeerFlow技能 : {s['deerflow_skills']}")
    print(f"    ├ Mem0 平面    : {s['mem0_plane']}")
    print(f"    ├ browser-use  : {s['browser_use_plane']}")
    print(f"    └ fabric能力   : {s['fabric_capability']}")
    print(f"  角色模板       : {s['roles']}  → DeerFlow 角色模板")
    regs = to_deerflow_registrations(cat)
    print(f"  DeerFlow注册项 : {len(regs)} (subagents + roles)")
    print("=" * 64)

    # 写文档
    md = render_placement_md(cat)
    out = Path(__file__).resolve().parents[1] / "docs" / "ASSET_PLACEMENT.md"
    out.write_text(md, encoding="utf-8")
    print(f"  ✅ 已生成 {out.relative_to(Path(__file__).resolve().parents[1])}")

    if do_register:
        print("\n>>> 尝试真实注册进 DeerFlow ...")
        res = register_all()
        print(f"  deerflow_available: {res['deerflow_available']}")
        print(f"  registered       : {res['registered']}")
        if res["error"]:
            print(f"  (未真注册，原因: {res['error']})")
    else:
        print("\n  (未加 --register：只产出归位目录与 DeerFlow 注册清单，未真注册)")
    print("=" * 64)


if __name__ == "__main__":
    main()
