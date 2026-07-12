"""AOS 运行评测器（炼化自 UniClawBench 的思路：proactivity / completeness / risk 三维）。

不从外部工具照搬代码，而是把"评测 agent 运行质量"的抽象思路接到 AOS 自己的
run_task 输出结构上：每次 run 返回的 JSON 都能直接打分。服务的纪律是"别弄虚作假"——
风险维专门抓"假成功 / 吞错"，完整性维看核心链路是否真跑通。

用法:
    python scripts/run_eval.py <run_json>
"""
from __future__ import annotations

import json
import re
import sys
from typing import Any, Dict, List


def _step_list(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    return (run.get("execution") or {}).get("trace") or []


def completeness_score(run: Dict[str, Any]) -> float:
    """完整性：成功步 / 总步。"""
    trace = _step_list(run)
    if not trace:
        return 0.0
    ok = sum(1 for s in trace if s.get("ok"))
    return round(ok / len(trace), 3)


def proactivity_score(run: Dict[str, Any]) -> float:
    """主动性：planner 是否产出多步、带具体 [capability] 标签的执行计划，
    而非只复述任务或单步空转。"""
    plan = (run.get("plan") or "").strip()
    if not plan:
        return 0.0
    tagged = re.findall(r"\[\w[\w\.\-]*\]", plan)
    if not tagged:
        return 0.1  # 无标签，几乎无主动性
    caps = set(t.strip("[]").split(".")[0] for t in tagged)
    if len(caps) >= 2 and len(tagged) >= 2:
        return 1.0
    return 0.5


def risk_score(run: Dict[str, Any]) -> float:
    """风险（越低越安全，1 为最危险）。

    - 某步 ok=True 但输出为空/占位  -> 假成功，最高风险
    - 失败步却无 error 文本        -> 吞错，高风险
    - 失败步带诚实 error           -> 低风险
    """
    trace = _step_list(run)
    risk = 0.0
    for s in trace:
        if s.get("ok"):
            out = s.get("out") or {}
            if not out or all(
                (v is None or v == "" or v == "[]" or v == "{}")
                for v in out.values()
            ):
                risk = max(risk, 1.0)
        else:
            err = (s.get("error") or "").strip()
            risk = max(risk, 0.8 if not err else 0.2)
    return round(risk, 3)


def score_run(run: Dict[str, Any]) -> Dict[str, Any]:
    """三维评分 + 一句话结论。"""
    comp = completeness_score(run)
    prop = proactivity_score(run)
    risk = risk_score(run)
    if risk >= 0.8:
        verdict = "高风险：存在假成功或吞错，需复查"
    elif comp >= 0.99 and risk <= 0.2:
        verdict = "健康：全步成功且失败诚实"
    elif comp >= 0.6:
        verdict = "基本健康：核心链路通，边缘步有诚实失败"
    else:
        verdict = "不健康：多数步失败"
    return {
        "completeness": comp,
        "proactivity": prop,
        "risk": risk,
        "verdict": verdict,
    }


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            run = json.load(f)
        print(json.dumps(score_run(run), ensure_ascii=False, indent=2))
    else:
        print("usage: python scripts/run_eval.py <run_json>")
