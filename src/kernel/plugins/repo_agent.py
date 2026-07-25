"""仓库自进化芯粒（action.repo）：让 AOS 自主环能安全操作自身代码仓库。

这是「把仓库和整个 AOS 项目结合起来」的核心落点——自主环不再只是搜/写/推，
而是能把验证过的改进**沉淀回代码仓库（git commit）**，形成可验证的自进化闭环：

    规划 → 改代码(action.code_exec) → 跑测试 → 反思沉淀(Meta-Trace)
         → 进化提交(action.repo) → 下一轮基于真实仓库状态变好

设计原则（AGENTS.md §5/§2.5/§9）：
- 芯粒隔离：git 失败不影响主环（故障熔断点），不抛异常到 autopilot。
- 权限即边界：只读操作(status/diff/log/branch)默认放行；写操作(commit/push/pr)
  必须显式确认(confirm=true)或设 AOS_REPO_WRITE / AOS_REPO_PUSH，绝不默认越权。
  push 默认关闭——避免自主环乱推远端。
- 诚实可验证：返回真实 git 输出，real=True 标注真实执行（非模拟），供前端
  「用了什么引擎 / 真实产出」直接展示，绝不谎报成功。
- 不触发重型链：InvokeResult/InvokeRequest 优先用 core.fabric.adapter，
  失败则本地兼容类 fallback，使芯粒在任意环境可运行（含无 aos venv 的沙箱）。
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    from core.fabric.adapter import InvokeResult, InvokeRequest
except Exception:  # 轻环境 fallback（字段与 autopilot 同构，类型弱一致）
    @dataclass
    class InvokeResult:
        ok: bool
        data: Optional[Dict[str, Any]] = None
        error: Optional[str] = None

    class InvokeRequest:
        def __init__(self, capability: str, payload: Dict[str, Any]):
            self.capability = capability
            self.payload = payload


# 敏感文件黑名单：commit 前若工作树含这些且未被 gitignore 则拒绝，防密钥入库
_SENSITIVE_SUFFIX = (".key", ".pem", ".pfx", ".env")
_SENSITIVE_NAME = (".env", "credentials.json", "secrets.yaml", "id_rsa", "id_dsa")
_WRITE_OPS = ("commit", "push", "pr")


def _is_write_op(op: str) -> bool:
    return op in _WRITE_OPS


def _match_sensitive(filename: str) -> bool:
    name = os.path.basename(filename)
    if name in _SENSITIVE_NAME:
        return True
    return name.endswith(_SENSITIVE_SUFFIX) or any(
        kw in name.lower() for kw in ("secret", "credential", "token")
    )


class RepoAgent:
    """受控的 git / gh 操作芯粒。所有方法返回 InvokeResult（{ok,data,error}）。"""

    def __init__(self, repo_root: Optional[str] = None):
        self.repo_root = repo_root or self._find_root()

    # ------------------------------------------------------------------ 路径
    @staticmethod
    def _find_root() -> str:
        env = os.environ.get("AOS_REPO_ROOT")
        if env and os.path.isdir(os.path.join(env, ".git")):
            return env
        # 从本文件向上找 .git（src/kernel/plugins -> 项目根）
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        cur = here
        for _ in range(6):
            if os.path.isdir(os.path.join(cur, ".git")):
                return cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        return os.getcwd()

    # ------------------------------------------------------------- 命令执行
    def _run(self, args: list, timeout: int = 60):
        """统一 git 执行；返回 (rc, out, err)。绝不抛异常。"""
        try:
            proc = subprocess.run(
                ["git", *args], cwd=self.repo_root,
                capture_output=True, text=True, timeout=timeout,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except Exception as e:  # noqa: BLE001
            return 1, "", str(e)

    def _run_gh(self, args: list, timeout: int = 60):
        """统一 gh CLI 执行（pr 用）；返回 (rc, out, err)。"""
        try:
            proc = subprocess.run(
                ["gh", *args], cwd=self.repo_root,
                capture_output=True, text=True, timeout=timeout,
            )
            return proc.returncode, proc.stdout or "", proc.stderr or ""
        except Exception as e:  # noqa: BLE001
            return 1, "", str(e)

    # -------------------------------------------------------------- 派发入口
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        op = (req.payload.get("operation") or "").lower()
        if not op:
            return InvokeResult(
                ok=False,
                error="repo: 缺少 operation（status/diff/log/branch/commit/push/pr）",
            )
        handler = {
            "status": self._op_status,
            "diff": self._op_diff,
            "log": self._op_log,
            "branch": self._op_branch,
            "commit": self._op_commit,
            "push": self._op_push,
            "pr": self._op_pr,
        }.get(op)
        if handler is None:
            return InvokeResult(ok=False, error=f"repo: 不支持的操作 {op}")
        try:
            return handler(req.payload)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"repo: {op} 执行异常: {e}")

    # ---------------------------------------------------------------- 只读
    def _op_status(self, payload: Dict[str, Any]) -> InvokeResult:
        rc, out, err = self._run(["status", "--porcelain=v1", "--branch"])
        branch = "unknown"
        for line in out.splitlines():
            if line.startswith("##"):
                branch = line[2:].strip().split("...")[0].strip()
                break
        return InvokeResult(
            ok=rc == 0,
            data={
                "operation": "status", "engine": "git", "real": True,
                "repo_root": self.repo_root, "branch": branch,
                "dirty": bool(out.strip()), "out": out or err,
            },
            error=None if rc == 0 else err,
        )

    def _op_diff(self, payload: Dict[str, Any]) -> InvokeResult:
        rc, out, err = self._run(["diff", "--stat"])
        return InvokeResult(
            ok=True,
            data={"operation": "diff", "engine": "git", "real": True,
                  "out": out or err},
        )

    def _op_log(self, payload: Dict[str, Any]) -> InvokeResult:
        n = int(payload.get("limit") or 5)
        rc, out, err = self._run(["log", f"-{n}", "--oneline", "--decorate"])
        return InvokeResult(
            ok=True,
            data={"operation": "log", "engine": "git", "real": True,
                  "out": out or err},
        )

    def _op_branch(self, payload: Dict[str, Any]) -> InvokeResult:
        rc, out, err = self._run(["branch", "-vv"])
        return InvokeResult(
            ok=True,
            data={"operation": "branch", "engine": "git", "real": True,
                  "out": out or err},
        )

    # ---------------------------------------------------------------- 写操作
    def _op_commit(self, payload: Dict[str, Any]) -> InvokeResult:
        # 权限门控（默认不放行写操作）
        if not (payload.get("confirm") or os.environ.get("AOS_REPO_WRITE") == "1"):
            return InvokeResult(
                ok=False,
                error="repo: 写操作需授权——传 confirm=true 或设 AOS_REPO_WRITE=1",
            )
        message = (payload.get("message") or "").strip()
        if len(message) < 5:
            return InvokeResult(ok=False, error="repo: commit 需提供有效 message（≥5字）")

        # 先检查敏感文件，通过后再暂存（避免敏感文件被 git add -A 加入暂存区）
        rc, st, _ = self._run(["status", "--porcelain"])
        for line in st.splitlines():
            f = line[3:].strip()
            if _match_sensitive(f):
                return InvokeResult(
                    ok=False,
                    error=f"repo: 检测到敏感文件 {f}，拒绝 commit（请先 gitignore）",
                )
        if not st.strip():
            return InvokeResult(ok=False, error="repo: 无改动可提交（working tree clean）")

        # 敏感检查通过，执行暂存
        self._run(["add", "-A"])

        rc, out, err = self._run(["commit", "-m", message])
        if rc != 0:
            return InvokeResult(ok=False, error=f"repo: commit 失败: {err or out}")

        # push（默认关，需显式授权，避免乱推远端）
        pushed = False
        if payload.get("push") and os.environ.get("AOS_REPO_PUSH") == "1":
            prc, pout, perr = self._run(["push"])
            pushed = prc == 0
            out = (out + "\n" + (pout or perr)).strip()
        return InvokeResult(
            ok=True,
            data={
                "operation": "commit", "engine": "git", "real": True,
                "message": message, "pushed": pushed, "out": out,
            },
        )

    def _op_push(self, payload: Dict[str, Any]) -> InvokeResult:
        if os.environ.get("AOS_REPO_PUSH") != "1":
            return InvokeResult(
                ok=False,
                error="repo: push 默认关闭，需设 AOS_REPO_PUSH=1（避免乱推远端）",
            )
        rc, out, err = self._run(["push"])
        return InvokeResult(
            ok=rc == 0,
            data={"operation": "push", "engine": "git", "real": True,
                  "out": out or err},
            error=None if rc == 0 else err,
        )

    def _op_pr(self, payload: Dict[str, Any]) -> InvokeResult:
        if not (payload.get("confirm") or os.environ.get("AOS_REPO_WRITE") == "1"):
            return InvokeResult(
                ok=False,
                error="repo: 建 PR 需授权（confirm=true / AOS_REPO_WRITE=1）",
            )
        title = (payload.get("message") or "AOS self-evolution").strip()[:120]
        body = payload.get("body") or "Auto-evolved by AOS autopilot (action.repo)."
        rc, out, err = self._run_gh(["pr", "create", "--title", title, "--body", body])
        return InvokeResult(
            ok=rc == 0,
            data={"operation": "pr", "engine": "gh", "real": True,
                  "out": out or err},
            error=None if rc == 0 else err,
        )

    # ------------------------------------------------------- 便捷状态查询
    def status(self) -> Dict[str, Any]:
        """供 /api/repo/status 直接调用，返回纯 dict。"""
        res = self.invoke(InvokeRequest(
            capability="action.repo", payload={"operation": "status"}))
        if not res.ok:
            return {"ok": False, "error": res.error}
        return {"ok": True, **(res.data or {})}


def get_repo_status() -> Dict[str, Any]:
    """模块级便捷函数：仓库当前状态（分支/是否脏/最近日志）。"""
    try:
        return RepoAgent().status()
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
