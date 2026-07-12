"""fabric 通电自检 CLI：诚实报告六个真实 OSS 引擎 live/dead。

用法（在仓库根目录 D:/AOS 下，用系统 Python 3.14）：
    py -3.14 -m scripts.fabric_scorecard
或  python scripts/fabric_scorecard.py
    python scripts/fabric_scorecard.py --isolation   # 按生产默认接线（Agnes/AG2 隔离）跑
    python scripts/fabric_scorecard.py --bootstrap-openclaw   # openclaw dead 时自动拉起网关(:18789)再复测

等价于 GET /api/fabric/health 的逻辑，但可在不启动服务时本地跑。
输出 JSON，便于 CI / 主机巡检。--isolation 会额外打印隔离可观测快照
（子进程 PID / 热备就绪 / 三闸门数字 / 上次恢复耗时）。
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
from kernel.wiring import build_fabric_hub


def main() -> int:
    use_isolation = "--isolation" in sys.argv[1:]
    bootstrap_oc = "--bootstrap-openclaw" in sys.argv[1:]
    used_env = _load_env()
    if use_isolation:
        # 按生产默认接线构建：Agnes/AG2 隔离进子进程，反映真实内核拓扑。
        hub = build_fabric_hub(isolate_heavy=True)
    else:
        hub = FabricHub()
    report = hub.health_report()
    # openclaw 自愈：dead 时尽力拉起网关(:18789)再复测。生产网关归 aos_supervisor
    # 管，这里提供运维按需一键自愈；沙箱无 openclaw 二进制则干净失败并报告死因。
    if bootstrap_oc and not report["adapters"].get("openclaw", {}).get("live"):
        from core.fabric.adapters.openclaw_adapter import OpenClawAdapter
        print("[bootstrap] openclaw 未存活，尝试自动拉起网关(:18789)...", file=sys.stderr)
        ok = OpenClawAdapter().ensure_gateway()
        print(f"[bootstrap] ensure_gateway -> {ok}", file=sys.stderr)
        report = hub.health_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    tag = "with .env keys" if used_env else "keyless (no .env)"
    iso_n = sum(1 for a in report["adapters"].values() if a.get("isolated"))
    print(
        f"\nSUMMARY: {report['live']}/{report['total']} engines live "
        f"[{tag}]  isolated={iso_n}",
        file=sys.stderr,
    )
    if use_isolation:
        import pprint
        print("\nISOLATION OBSERVABILITY:", file=sys.stderr)
        pprint.pprint(hub.isolation_summary(), stream=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
