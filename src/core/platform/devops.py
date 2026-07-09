"""
AOS v5.0 — DevOps 流水线 (Pipeline)

对标蓝图 DEVOPS(DevOps 流水线)。满足蓝图节点: DEVOPS。
设计原则 (严谨 + 开放 + 灵活):
  - 步骤是数据: {name, run(callable|shell), on_fail(abort|continue)}。
  - 执行时记录每步 status/output/duration; on_fail=abort 在失败即停。
  - 结果可经 on_result 回调持久化 (如写 DB/事件), 默认仅返回汇总。
"""

import logging
import shlex
import subprocess
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, name: str, steps: Optional[List[Dict[str, Any]]] = None,
                 on_result: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.name = name
        self.steps = steps or []
        self.on_result = on_result

    def add(self, name: str, run: Any, on_fail: str = "abort", shell: bool = False) -> "Pipeline":
        # shell=True 为高危显式 opt-in: 仅限可信静态命令 (禁止拼接不可信输入)。
        self.steps.append({"name": name, "run": run, "on_fail": on_fail, "shell": shell})
        return self

    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        run = step["run"]
        start = time.time()
        try:
            if isinstance(run, str):
                # 安全默认: 关闭 shell, 用 shlex 拆分为 argv, 消除命令注入
                # (; | && $() `` 等元字符不再被 shell 解释)。
                # 仅当 step 显式声明 shell=True (高信任、确需管道/重定向/环境变量展开)
                # 才回退到 shell=True —— 这属于高危操作, 仅限可信静态命令。
                use_shell = bool(step.get("shell", False))
                if use_shell:
                    argv: Any = run
                    logger.warning(
                        "Pipeline 步骤 %r 以 shell=True 运行命令, 属高危操作, "
                        "仅限可信静态命令 (禁止拼接不可信输入)", step.get("name")
                    )
                else:
                    try:
                        argv = shlex.split(run)
                    except ValueError as ve:
                        return {
                            "name": step["name"], "ok": False,
                            "output": f"命令解析失败 (非法引号/语法): {ve}",
                            "duration_ms": 0.0, "on_fail": step.get("on_fail", "abort"),
                        }
                proc = subprocess.run(argv, shell=use_shell, capture_output=True, text=True, timeout=300)
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
