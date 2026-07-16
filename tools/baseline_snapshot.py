#!/usr/bin/env python3
"""生成 AGENTS.md 的 §0.5 基线快照表（让"宪法自己也不能弄虚"）。

设计原则（见 AGENTS.md §1.9 可验证即真理）：
- 所有数字**真跑得出**，不手抄、不估算。
- 轻量模式（默认）：适配器数（不 spawn 子进程）+ 测试收集数，秒级完成。
- 重量模式（AOS_BASELINE_HEAVY=1）：额外真跑 `FabricHub.health_report()` 拿 live/dead、
  真跑 `pytest --cov=src` 拿覆盖率。耗时数分钟，供 CI 定时/commit 钩子使用。

用法：
    python tools/baseline_snapshot.py                 # 轻量，更新适配器/测试数
    AOS_BASELINE_HEAVY=1 python tools/baseline_snapshot.py   # 含 live/dead + 覆盖率
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS = REPO / "AGENTS.md"
SRC = REPO / "src"
HEAVY = os.environ.get("AOS_BASELINE_HEAVY") == "1"

# §0.5 表用这对标记包裹，重跑时原地替换，不碰其它内容。
START = "<!-- BASELINE_START -->"
END = "<!-- BASELINE_END -->"


def _run(cmd: list[str], timeout: int = 540) -> str:
    try:
        cp = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(SRC), "PYTHONIOENCODING": "utf-8"},
        )
        return cp.stdout + cp.stderr
    except Exception as e:  # noqa: BLE001
        return f"(error: {e})"


def adapter_total() -> int:
    """kernel FabricHub 注册适配器数 = `_ADAPTERS`(18) + orchestrator(运行时自动注册)。

    不构造 FabricHub（构造会 spawn agnes/ag2 子进程 + prewarm，耗时 ~3min）。
    """
    sys.path.insert(0, str(SRC))
    from kernel.plugins import fabric_hub  # noqa: E402
    return len(fabric_hub._ADAPTERS) + 1


def test_collected() -> str:
    out = _run([sys.executable, "-m", "pytest", "--co", "-q"], timeout=200)
    m = re.search(r"(\d+)\s+tests? collected", out)
    return m.group(1) if m else "?"


def live_dead() -> tuple[str, str]:
    if not HEAVY:
        return ("?", "?")
    sys.path.insert(0, str(SRC))
    try:
        from kernel.plugins.fabric_hub import FabricHub  # noqa: E402
        hub = FabricHub()
        r = hub.health_report()
        dead = [k for k, v in r["adapters"].items() if not v["live"]]
        return str(r["live"]), str(len(dead))
    except Exception as e:  # noqa: BLE001
        return ("?", f"err:{e!r}")


def coverage_pct() -> str:
    if not HEAVY:
        return "?"
    out = _run([sys.executable, "-m", "pytest", "--cov=src",
                "--cov-report=term", "-q"], timeout=590)
    # pytest-cov 末尾: "TOTAL      22856  16029   30%"
    m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", out)
    return m.group(1) if m else "?"


def build_table(total: int, collected: str, live: str, dead: str, cov: str,
                 adapters_n: int) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    mode = "CI 自动生成(HEAVY)" if HEAVY else "手动生成(轻量)"
    cov_note = (f"`pytest --cov=src` 实测" if HEAVY
                else "轻量模式未测；HEAVY 模式实测见 §5 质量门下限")
    live_note = (f"`FabricHub.health_report()` 实测" if HEAVY
                 else "重跑需 `AOS_BASELINE_HEAVY=1`")
    return f"""## 0.5 基线快照（{when}，{mode}）

> 任何 AI / 用户进场第一秒应读到"现在到底行不行"，而非手写叙事。
> 本表由 `tools/baseline_snapshot.py` 真实测算后写入；轻量模式测适配器/测试数，
> `AOS_BASELINE_HEAVY=1` 额外测 live/dead 与覆盖率。

| 项 | 数值 | 备注 |
|----|------|------|
| 适配器总数 | {total} | kernel FabricHub `_ADAPTERS`({adapters_n}) + orchestrator(自动注册) |
| live | {live} | {live_note} |
| dead | {dead} | 典型无 key 环境见 §7（openclaw/ag2/litellm/mem0/lfm2） |
| 测试 | {collected} collected | `pytest --co -q` |
| 覆盖率 | {cov}% | {cov_note} |
| brain.fabric | 优雅降级 None | `core/brain.py:_init_fabric`(875) import 失败即 `fabric=None`，双轨未合 |
| 生成时间 | {when} | `python tools/baseline_snapshot.py` |
"""


def main() -> int:
    sys.path.insert(0, str(SRC))
    from kernel.plugins import fabric_hub
    total = adapter_total()
    adapters_n = len(fabric_hub._ADAPTERS)
    collected = test_collected()
    live, dead = live_dead()
    cov = coverage_pct()
    table = build_table(total, collected, live, dead, cov, adapters_n)

    text = AGENTS.read_text(encoding="utf-8")
    block = f"{START}\n{table}{END}\n"
    if START in text and END in text:
        new_text = re.sub(re.escape(START) + r".*?" + re.escape(END),
                          block.strip(), text, flags=re.DOTALL)
    else:
        # 首次：在 "## 1. 九大核心理念" 之前插入带标记的 §0.5。
        new_text = text.replace("## 1. 九大核心理念",
                                block + "\n## 1. 九大核心理念", 1)
    AGENTS.write_text(new_text, encoding="utf-8")
    print(f"[baseline] adapters={total} tests={collected} "
          f"live={live} dead={dead} coverage={cov}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
