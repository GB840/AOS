"""fabric 通电自检（带 .env 加载版）。

与 fabric_scorecard.py 的区别：先读取 D:/AOS/.env 注入 os.environ，
再跑 honest scorecard。这样 ag2 这类需要 API key 的适配器才能拿到
key 翻绿。密钥只在进程内读取，绝不打印到输出。

输出：每个引擎的 engine_id / live / 主要能力，以及 live/total 汇总。
"""
from __future__ import annotations

import json
import os
import sys

REPO = "D:/AOS"
ENV_PATH = os.path.join(REPO, ".env")
sys.path.insert(0, os.path.join(REPO, "src"))


def _load_env(path: str) -> None:
    """把 .env 的 KEY=VALUE 注入 os.environ（不覆盖已有值）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


def main() -> int:
    _load_env(ENV_PATH)
    from kernel.plugins.fabric_hub import FabricHub

    hub = FabricHub()
    report = hub.health_report()

    # 只输出引擎判活信息，绝不打印密钥/配置值
    curated = {
        "total": report["total"],
        "live": report["live"],
        "engines": [
            {
                "id": eid,
                "live": e["live"],
                "capabilities": e.get("capabilities", []),
                "error": e.get("error"),  # 仅 dead 时可能有简短原因
            }
            for eid, e in report["adapters"].items()
        ],
    }
    print(json.dumps(curated, ensure_ascii=False, indent=2))
    print(f"\nSUMMARY: {report['live']}/{report['total']} engines live", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
