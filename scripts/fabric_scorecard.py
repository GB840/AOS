"""fabric 通电自检 CLI：诚实报告六个真实 OSS 引擎 live/dead。

用法（在仓库根目录 D:/AOS 下，用系统 Python 3.14）：
    py -3.14 -m scripts.fabric_scorecard
或  python scripts/fabric_scorecard.py

等价于 GET /api/fabric/health 的逻辑，但可在不启动服务时本地跑。
输出 JSON，便于 CI / 主机巡检。
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "D:/AOS/src")

from kernel.plugins.fabric_hub import FabricHub


def main() -> int:
    hub = FabricHub()
    report = hub.health_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        f"\nSUMMARY: {report['live']}/{report['total']} engines live",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
