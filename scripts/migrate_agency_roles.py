#!/usr/bin/env python3
"""Agency Roles 收口迁移脚本（默认 dry-run，不修改任何文件）。

背景：分析器已确认 269 个角色文件 100% 只用 `brain.chat()`，模式完全同构：
    from core import get_brain
    brain = get_brain()
    ...
    result = brain.chat(prompt, model="default")

收口目标：把上面的 get_brain 入口换成统一薄壳，由运行时 flag 决定走内核还是 brain：
    from skills.agency_roles import get_agency_runtime
    rt = get_agency_runtime(role_id=self.NAME)
    ...
    result = rt.chat(prompt, model="default")

安全性（关键）：即使一次性重写全部 269 个文件，运行时行为也**完全不变**——
flag AOS_USE_KERNEL_FOR_ROLES 默认关闭 → get_agency_runtime 返回 _LegacyRuntime
→ 仍走 get_brain()。所以「重写」与「切流」解耦：先全量重写（零风险），
再用运行时 flag/allowlist 灰度切流，回滚只需关 flag，无需回退文件。

用法：
    python scripts/migrate_agency_roles.py                 # dry-run，打印将改哪些
    python scripts/migrate_agency_roles.py --apply         # 真正写入
    python scripts/migrate_agency_roles.py --role 前端开发者  # 只处理一个角色
    python scripts/migrate_agency_roles.py --apply --backup  # 写入前备份
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

ROLES_DIR = Path(__file__).resolve().parent.parent / "src" / "skills" / "agency_roles"
SKIP = {"__init__.py", "_kernel_bridge.py"}

import_re = re.compile(r"^(\s*)from core import get_brain\s*$", re.M)
assign_re = re.compile(r"^(\s*)(\w+)\s*=\s*get_brain\s*\(\s*\)\s*$", re.M)


def transform(text: str) -> tuple[str, bool]:
    """返回 (新文本, 是否改动)。仅处理同构模式。"""
    var = None
    for m in assign_re.finditer(text):
        var = m.group(2)
        break
    if var is None:
        return text, False

    new = text
    # 1) import 行
    new = import_re.sub(r"\1from skills.agency_roles import get_agency_runtime", new)
    # 2) 赋值行
    new = re.sub(
        r"^(\s*){0}\s*=\s*get_brain\s*\(\s*\)\s*$".format(re.escape(var)),
        r"\1rt = get_agency_runtime(role_id=self.NAME)",
        new, count=1, flags=re.M,
    )
    # 3) 所有 var.chat( → rt.chat(
    new = re.sub(r"\b{0}\.chat\(".format(re.escape(var)), "rt.chat(", new)
    return new, (new != text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写入（默认仅 dry-run）")
    ap.add_argument("--role", help="只处理指定角色文件（按文件名或 NAME）")
    ap.add_argument("--backup", action="store_true", help="写入前备份到 _migrate_backup/")
    args = ap.parse_args()

    files = sorted(p for p in ROLES_DIR.glob("*.py") if p.name not in SKIP)
    if args.role:
        files = [p for p in files if args.role in (p.stem, p.name)]
        if not files:
            print(f"[warn] 未找到匹配角色: {args.role}")
            return

    changed = []
    skipped = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        new, did = transform(text)
        if did:
            changed.append(p)
            if args.apply:
                if args.backup:
                    bk = ROLES_DIR / "_migrate_backup" / p.name
                    bk.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(p, bk)
                p.write_text(new, encoding="utf-8")
                print(f"  [APPLIED] {p.name}")
            else:
                print(f"  [dry-run] {p.name}  → 将改为 rt = get_agency_runtime(role_id=self.NAME)")
        else:
            skipped.append(p)

    print(f"\n汇总: 可改写 {len(changed)} / 跳过 {len(skipped)} (共扫描 {len(files)})")
    if not args.apply:
        print("（dry-run 模式，未写入任何文件。加 --apply 才真正改写。）")


if __name__ == "__main__":
    main()
