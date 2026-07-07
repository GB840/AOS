"""
AOS v5.0 — DevOps 流水线 (Pipeline)

对标蓝图 DEVOPS(DevOps 流水线)。满足蓝图节点: DEVOPS。
设计原则 (严谨 + 开放 + 灵活):
  - 步骤是数据: {name, run(callable|shell), on_fail(abort|continue)}。
  - 执行时记录每步 status/output/duration; on_fail=abort 在失败即停。
  - 结果可经 on_result 回调持久化 (如写 DB/事件), 默认仅返回汇总。
"""

import subprocess
import time
import traceback
from typing import Any, Callable, Dict, List, Optional


class Pipeline:
    def __init__(self, name: str, steps: Optional[List[Dict[str, Any]]] = None,
                 on_result: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.name = name
        self.steps = steps or []
        self.on_result = on_result

    def add(self, name: str, run: Any, on_fail: str = "abort") -> "Pipeline":
        self.steps.append({"name": name, "run": run, "on_fail": on_fail})
        return self

    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        run = step["run"]
        start = time.time()
        try:
            if isinstance(run, str):
                proc = subprocess.run(run, shell=True, capture_output=True, text=True, timeout=300)
                ok = proc.returncode == 0
                output = proc.stdout + proc.stderr
            elif callable(run):
                result = run()
                ok = bool(result) if isinstance(result, bool) else True
                output = str(result)
            else:
                ok, output = False, "step.run 既非命令也非可调用"
        except Exception as e:  # pragma: no cover - 步骤异常记为失败
            ok = False
            output = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        dur = round((time.time() - start) * 1000, 2)
        return {"name": step["name"], "ok": ok, "output": output, "duration_ms": dur,
                "on_fail": step.get("on_fail", "abort")}

    def run(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        context = context or {}
        results: List[Dict[str, Any]] = []
        aborted = False
        for step in self.steps:
            rec = self._execute_step(step)
            rec["context"] = context
            results.append(rec)
            if self.on_result:
                try:
                    self.on_result(rec)
                except Exception:  # pragma: no cover - 回调异常不影响流水线
                    pass
            if not rec["ok"] and rec.get("on_fail") == "abort":
                aborted = True
                break
        return {
            "name": self.name,
            "aborted": aborted,
            "success": all(r["ok"] for r in results),
            "steps": results,
        }
