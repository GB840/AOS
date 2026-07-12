"""fabric 通电自检 CLI：诚实报告六个真实 OSS 引擎 live/dead。

用法（在仓库根目录 D:/AOS 下，用系统 Python 3.14）：
    py -3.14 -m scripts.fabric_scorecard
或  python scripts/fabric_scorecard.py

等价于 GET /api/fabric/health 的逻辑，但可在不启动服务时本地跑。
输出 JSON，便于 CI / 主机巡检。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "D:/AOS/src")


def _load_env(path: str = ".env") -> bool:
    """best-effort 加载 .env（不覆盖已存在的环境变量）。本地开发用；CI 无 .env 时退回 keyless 结构检查。"""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)
        return True
    except Exception:
        return False


from kernel.plugins.fabric_hub import FabricHub


def main() -> int:
    used_env = _load_env()
    hub = FabricHub()
    report = hub.health_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    tag = "with .env keys" if used_env else "keyless (no .env)"
    print(
        f"\nSUMMARY: {report['live']}/{report['total']} engines live [{tag}]",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
