"""白盒进化蒸馏引擎演示（任务272 / 白皮书 3.3）。

展示 AOS 新范式的『白盒进化』：从多次执行 Trace 蒸馏出不可靠引擎，
产出可回读路由决策的沉底建议——进化来自可复核证据，而非盲目改代码
（对比 HyperAgents 直接改自己运行时源码）。

运行:
  cd D:/AOS
  PYTHONPATH=/d/AOS/src python examples/evolution_distiller_demo.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from kernel.evolution_distiller import EvolutionDistiller


def _trace(cap, eng, ok, err=""):
    return {"steps": [{"capability": cap, "engine": eng, "ok": ok, "error": err}]}


def demo():
    store = os.path.join(os.path.dirname(__file__), "evolution_distill.jsonl")
    if os.path.exists(store):
        os.remove(store)
    dist = EvolutionDistiller(store)

    print("=" * 66)
    print("AOS 新范式演示：白盒进化蒸馏引擎")
    print("=" * 66)

    # 模拟多个真实任务的执行 Trace（白盒证据）
    traces = [
        _trace("web.search", "bing", False, "timeout 30s"),
        _trace("web.search", "bing", False, "503 timeout"),
        _trace("web.search", "bing", True),
        _trace("web.search", "bing", False, "connection reset"),
        _trace("web.search", "bing", False, "timeout"),
        _trace("web.search", "bing", True),
        _trace("web.search", "bing", False, "timeout"),
        _trace("inference.llm", "mistralrs", True),
        _trace("inference.llm", "mistralrs", True),
        _trace("inference.llm", "mistralrs", True),
    ]
    print(f"\n喂入 {len(traces)} 个执行 Trace（白盒证据）...")
    for tr in traces:
        dist.ingest(tr)

    recs = dist.distill()
    print(f"\n蒸馏结果：发现 {len(recs)} 个不可靠引擎建议沉底")
    for r in recs:
        print(f"  - 沉底 [{r['capability']}::{r['engine']}] "
              f"失败率 {r['fail_rate']}（{r['reason']}）")
        print(f"    最近错误: {r['last_error']}")

    reliable = dist.reliable_engines()
    print(f"\n稳定引擎（不沉底）: {reliable}")

    print("\n" + "=" * 66)
    print("结论: 系统从真实 Trace 统计出『bing 在 web.search 不可靠』，")
    print("      自动产出沉底建议供路由决策——这是白盒、可复核、")
    print("      可回退的进化，不修改任何运行时代码。")
    print("=" * 66)


if __name__ == "__main__":
    demo()
