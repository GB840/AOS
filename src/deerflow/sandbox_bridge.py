"""
DeerFlow Sandbox Bridge -- exposes the REAL DeerFlow sandbox subsystem to AOS.

Wraps:
  - deerflow.sandbox.sandbox.Sandbox (ABC: execute_command, read_file, write_file, glob, grep, etc.)
  - deerflow.sandbox.sandbox_provider.SandboxProvider (acquire/get/release lifecycle)
  - deerflow.sandbox.security (host bash gating)
  - deerflow.sandbox.middleware.SandboxMiddleware

All imports resolve to REAL DeerFlow 2.0 source, NOT stubs.
"""

import logging
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

from deerflow.path_detect import setup_deerflow_env

_DEERFLOW_SRC = setup_deerflow_env()

if _DEERFLOW_SRC:
    try:
        # ---- REAL DeerFlow imports ----
        from deerflow.sandbox.sandbox import Sandbox as _DeerFlowSandbox
        from deerflow.sandbox.sandbox_provider import (
            SandboxProvider as _DeerFlowSandboxProvider,
            get_sandbox_provider,
            reset_sandbox_provider,
            shutdown_sandbox_provider,
            set_sandbox_provider,
        )
        from deerflow.sandbox.security import (
            uses_local_sandbox_provider,
            is_host_bash_allowed,
            LOCAL_HOST_BASH_DISABLED_MESSAGE,
            LOCAL_BASH_SUBAGENT_DISABLED_MESSAGE,
        )
        from deerflow.sandbox.search import GrepMatch
        logger.info("✅ DeerFlow Sandbox Bridge 加载成功")
    except ImportError as e:
        logger.warning(f"❌ DeerFlow Sandbox Bridge 导入失败: {e}")
        _DEERFLOW_SRC = None
else:
    logger.warning("⚠️ DeerFlow 源码路径未检测到")


class AOSSandboxBridge:
    """AOS-facing sandbox bridge -- unified API for code execution.

    Provides a simple Pythonic interface to the DeerFlow sandbox subsystem:
    - execute_command(bash_cmd) -> stdout
    - read_file(path) -> content
    - write_file(path, content)
    - list_dir(path) -> file list
    - glob(pattern) -> matching paths
    - grep(pattern) -> matches

    Uses DeerFlow's SandboxProvider lifecycle (acquire/get/release).
    """

    def __init__(self, thread_id: str = None, user_id: str = None):
        self._provider: Optional[_DeerFlowSandboxProvider] = None
        self._sandbox: Optional[_DeerFlowSandbox] = None
        self._sandbox_id: Optional[str] = None
        self._thread_id = thread_id or "aos-default"
        self._user_id = user_id or "aos-user"
        self._acquired = False

    @property
    def is_ready(self) -> bool:
        return self._acquired and self._sandbox is not None

    def acquire(self) -> str:
        """Acquire a sandbox from the provider. Returns sandbox_id."""
        if self._acquired:
            return self._sandbox_id

        self._provider = get_sandbox_provider()
        self._sandbox_id = self._provider.acquire(
            thread_id=self._thread_id, user_id=self._user_id
        )
        self._sandbox = self._provider.get(self._sandbox_id)
        self._acquired = True
        logger.info("Sandbox acquired: id=%s, provider=%s",
                     self._sandbox_id, type(self._provider).__name__)
        return self._sandbox_id

    def release(self):
        """Release the sandbox back to the provider."""
        if self._acquired and self._provider and self._sandbox_id:
            self._provider.release(self._sandbox_id)
            logger.info("Sandbox released: id=%s", self._sandbox_id)
        self._sandbox = None
        self._sandbox_id = None
        self._acquired = False

    # ---- Delegated Sandbox Operations ----

    def execute_command(self, command: str) -> str:
        """Execute a bash command in the sandbox. Returns stdout/stderr."""
        self._ensure_acquired()
        return self._sandbox.execute_command(command)

    def read_file(self, path: str) -> str:
        """Read text content of a file in the sandbox."""
        self._ensure_acquired()
        return self._sandbox.read_file(path)

    def write_file(self, path: str, content: str, append: bool = False) -> None:
        """Write text content to a file in the sandbox."""
        self._ensure_acquired()
        self._sandbox.write_file(path, content, append=append)

    def download_file(self, path: str) -> bytes:
        """Download binary content of a file."""
        self._ensure_acquired()
        return self._sandbox.download_file(path)

    def list_dir(self, path: str, max_depth: int = 2) -> List[str]:
        """List directory contents."""
        self._ensure_acquired()
        return self._sandbox.list_dir(path, max_depth=max_depth)

    def glob(self, path: str, pattern: str, *,
             include_dirs: bool = False,
             max_results: int = 200) -> Tuple[List[str], bool]:
        """Glob for files matching a pattern."""
        self._ensure_acquired()
        return self._sandbox.glob(path, pattern,
                                   include_dirs=include_dirs,
                                   max_results=max_results)

    def grep(self, path: str, pattern: str, *,
             glob: str = None, literal: bool = False,
             case_sensitive: bool = False,
             max_results: int = 100) -> Tuple[List[GrepMatch], bool]:
        """Search file contents with ripgrep."""
        self._ensure_acquired()
        return self._sandbox.grep(path, pattern,
                                   glob=glob, literal=literal,
                                   case_sensitive=case_sensitive,
                                   max_results=max_results)

    def update_file(self, path: str, content: bytes) -> None:
        """Update a file with binary content."""
        self._ensure_acquired()
        self._sandbox.update_file(path, content)

    # ---- Security Checks ----

    def is_local_provider(self) -> bool:
        """Check if running on local (non-isolated) sandbox provider."""
        return uses_local_sandbox_provider()

    def is_bash_allowed(self) -> bool:
        """Check if host bash execution is permitted."""
        return is_host_bash_allowed()

    def _ensure_acquired(self):
        if not self._acquired:
            self.acquire()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

    def shutdown(self):
        """Release sandbox and shut down provider."""
        self.release()
        shutdown_sandbox_provider()


# ---- Convenience functions ----

def create_sandbox(thread_id: str = None, user_id: str = None) -> AOSSandboxBridge:
    """Create and acquire an AOS sandbox bridge."""
    bridge = AOSSandboxBridge(thread_id=thread_id, user_id=user_id)
    bridge.acquire()
    return bridge


def sandbox_context(thread_id: str = None, user_id: str = None):
    """Context manager for safe sandbox execution.

    Usage:
        with sandbox_context() as sb:
            result = sb.execute_command("ls -la")
    """
    return AOSSandboxBridge(thread_id=thread_id, user_id=user_id)
