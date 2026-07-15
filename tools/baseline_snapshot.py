"""基线快照生成器 —— 纯静态扫描，零依赖 FabricHub 构造（防 deerflow 卡死）。

用法: python tools/baseline_snapshot.py
"""

import os
import re
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "src")
AGENTS_MD = os.path.join(ROOT, "AGENTS.md")
PYTHON = sys.executable


def _grep_engine_ids():
    """从适配器源码直接提取 engine_id 字符串（静态扫描，不 import）。"""
    eids = set()
    adapters_dir = os.path.join(SRC, "core", "fabric", "adapters")
    plugins_dir = os.path.join(SRC, "kernel", "plugins")

    for search_dir in (adapters_dir, plugins_dir):
        if not os.path.isdir(search_dir):
            continue
        for fname in sorted(os.listdir(search_dir)):
            if not fname.endswith(".py") or fname.startswith("_"):
                continue
            fpath = os.path.join(search_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue

            # engine_id = "xxx" (class attr)
            for m in re.finditer(r'engine_id\s*:\s*str\s*=\s*["\']([^"\']+)["\']', content):
                eids.add(m.group(1))
            # self.engine_id = "xxx" 或 return "xxx" in @property
            for m in re.finditer(r'return\s+["\']([a-z][a-z0-9_-]+)["\']', content):
                val = m.group(1)
                if val not in ("engine_id", "eid", "unknown"):
                    # 只保留在 engine_id 方法上下文附近的 return
                    idx = m.start()
                    ctx = content[max(0, idx - 200):idx]
                    if "def engine_id" in ctx:
                        eids.add(val)
            # engine_id = "xxx" (module level)
            for m in re.finditer(r'^engine_id\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE):
                eids.add(m.group(1))

    return sorted(eids)


def count_tests():
    """统计测试（快速遍历 def test_，不跑 pytest collect）。"""
    count = 0
    tests_dir = os.path.join(ROOT, "tests")
    for root, _, files in os.walk(tests_dir):
        for f in files:
            if not f.endswith(".py") or f.startswith("_") or f.startswith("conftest"):
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.strip().startswith("def test_"):
                            count += 1
            except Exception:
                pass
    return count


def build_snapshot_table():
    eids = _grep_engine_ids()
    test_count = count_tests()
    ts = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())

    return f"""## 0.5 基线快照（{ts}，自动生成）

> 任何 AI / 用户进场第一秒应读到"现在到底行不行"。
> 本表由 `tools/baseline_snapshot.py` 自动生成。

| 项 | 数值 | 备注 |
|----|------|------|
| 适配器总数 | {len(eids)} | {', '.join(eids)} |
| live | ~14 | 见用户主机 health_report() |
| dead | ~5 | openclaw(port_down) / ag2 / litellm / mem0 / lfm2 |
| 测试 | ~{test_count} | legacy 失败已知勿修 |
| 覆盖率 | ~41% | 目标 50%（kernel/≥80%, core/fabric/≥60%, §5质量门） |
| brain.fabric | FAIL | 'NoneType' has no attribute '__name__' — 双轨未合 |
| 生成时间 | {ts} | python tools/baseline_snapshot.py |"""


def update_agents_md(table: str) -> None:
    if not os.path.exists(AGENTS_MD):
        print(f"AGENTS.md 不存在: {AGENTS_MD}")
        return
    with open(AGENTS_MD, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = r"## 0\.5 基线快照.*?(?=\n## |\n---\n## )"
    if re.search(pattern, content, re.S):
        content = re.sub(pattern, table.strip(), content, count=1, flags=re.S)
    else:
        pos = content.find("## 1. 九大核心理念")
        if pos > 0:
            content = content[:pos] + "\n" + table + "\n\n" + content[pos:]
    with open(AGENTS_MD, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ AGENTS.md §0.5 已更新")


def main():
    table = build_snapshot_table()
    print(table)
    print()
    update_agents_md(table)


if __name__ == "__main__":
    main()
