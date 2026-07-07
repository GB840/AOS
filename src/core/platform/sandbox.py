"""
AOS v5.0 — 执行沙箱 (Sandbox)

对标蓝图 FABRIC / WASM / PYTHON。满足蓝图节点: FABRIC(执行层) + WASM/PYTHON 沙箱。
设计原则 (严谨 + 开放 + 灵活):
  - Sandbox 抽象基类: 任何运行时 (Python/WASM/容器) 都实现 run()。
  - PythonSandbox: 子进程隔离 + 超时 + 可选 import 白名单 (AST 静态校验)。
    说明: 这是进程级隔离, 并非强 capability 沙箱; 生产强隔离应叠加容器/WASM。
  - WasmSandbox: 接口就绪, 依赖 wasmtime/运行时时启用; 未安装时明确报错 (开放, 不假装)。
"""

import ast
import logging
import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Sandbox(ABC):
    @abstractmethod
    def run(self, code: str, timeout: float = 5.0, **kwargs) -> Dict[str, Any]:
        """执行 code, 返回 {ok, stdout, stderr, returncode, error}。"""

    @property
    @abstractmethod
    def kind(self) -> str:
        ...


class PythonSandbox(Sandbox):
    """子进程隔离的 Python 执行沙箱。"""

    def __init__(self, allow_imports: Optional[List[str]] = None):
        # allow_imports=None 表示不限制 (仅做超时隔离); 传列表则强制白名单。
        self.allow_imports = allow_imports

    @property
    def kind(self) -> str:
        return "python"

    def _check_imports(self, code: str) -> Optional[str]:
        if not self.allow_imports:
            return None
        allowed = set(self.allow_imports)
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    if n.name.split(".")[0] not in allowed:
                        return f"import 不在白名单: {n.name}"
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod and mod not in allowed:
                    return f"from import 不在白名单: {node.module}"
        return None

    def run(self, code: str, timeout: float = 5.0, **kwargs) -> Dict[str, Any]:
        bad = self._check_imports(code)
        if bad:
            return {"ok": False, "error": bad, "kind": self.kind}
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=timeout,
            )
            return {
                "ok": proc.returncode == 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "returncode": proc.returncode,
                "kind": self.kind,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"timeout after {timeout}s", "kind": self.kind}
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": str(e), "kind": self.kind}


class WasmSandbox(Sandbox):
    """WASM 沙箱接口。需要 wasmtime/运行时; 未安装时明确报错 (开放, 不假装可用)。"""

    def __init__(self, runtime: str = "wasmtime"):
        self.runtime = runtime
        self._available = self._probe()

    def _probe(self) -> bool:
        try:
            if self.runtime == "wasmtime":
                import wasmtime  # type: ignore
                return True
        except Exception:
            pass
        return False

    @property
    def kind(self) -> str:
        return "wasm"

    def run(self, code: str, timeout: float = 5.0, **kwargs) -> Dict[str, Any]:
        if not self._available:
            return {
                "ok": False,
                "error": f"WASM 运行时未安装 (需 wasmtime)。安装后启用: pip install wasmtime",
                "kind": self.kind,
            }
        # 接口就绪: 运行时存在时, 此处接入 wasmtime 加载/实例化/调用逻辑。
        # 当前保持接口完整, 具体 wasm 模块加载交由调用方提供 bytes。
        return {
            "ok": False,
            "error": "WASM 模块加载需调用方提供 wasm bytes; 接口已就绪。",
            "kind": self.kind,
        }
