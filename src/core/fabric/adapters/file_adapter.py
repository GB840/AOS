"""文件操作适配器 —— AOS fabric 的 FILE_ACCESS 平面。

把文件读写能力暴露为 fabric adapter，使 OrchestrationChiplet 能经 route()
把 action.file_access 步骤委派给真实文件系统。这是「个人 AI 编程助手」
场景的核心能力——读代码、写代码、列目录。

设计原则：安全第一。
- 所有操作限制在 workspace_root 内（默认 data/workspaces/fabric/）
- 路径遍历防护：拒绝 ../ 和绝对路径
- 不编造内容：文件不存在就如实失败
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)


class FileAdapter(BaseAgentAdapter):
    """文件读写能力供给方。"""

    def __init__(self) -> None:
        from utils.config import config
        self._root = Path(config.DATA_DIR) / "workspaces" / "fabric"
        self._root.mkdir(parents=True, exist_ok=True)
        logger.info("FileAdapter: workspace root = %s", self._root)

    @property
    def engine_id(self) -> str:
        return "file-io"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.FILE_ACCESS]

    def health(self) -> bool:
        return self._root.exists() and self._root.is_dir()

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        action = payload.get("action", "read")

        if action == "read":
            return self._read(payload)
        elif action == "write":
            return self._write(payload)
        elif action == "list":
            return self._list(payload)
        else:
            return InvokeResult(ok=False, error=f"未知操作: {action}")

    def _safe_path(self, file_path: str) -> Path | None:
        """安全路径解析：确保解析后的路径在 workspace_root 内。"""
        if not file_path:
            return None
        # 拒绝绝对路径和路径遍历
        if os.path.isabs(file_path) or ".." in Path(file_path).parts:
            return None
        full = (self._root / file_path).resolve()
        try:
            full.relative_to(self._root.resolve())
        except ValueError:
            return None
        return full

    def _read(self, payload: dict[str, Any]) -> InvokeResult:
        file_path = payload.get("path") or payload.get("file") or ""
        full = self._safe_path(file_path)
        if full is None:
            return InvokeResult(ok=False, error="非法路径或路径越界")
        if not full.exists():
            return InvokeResult(ok=False, error=f"文件不存在: {file_path}")
        try:
            content = full.read_text(encoding="utf-8")
            return InvokeResult(ok=True, data={
                "content": content,
                "path": file_path,
                "size": len(content),
            })
        except Exception as e:
            return InvokeResult(ok=False, error=str(e))

    def _write(self, payload: dict[str, Any]) -> InvokeResult:
        file_path = payload.get("path") or payload.get("file") or ""
        content = payload.get("content") or payload.get("data") or ""
        full = self._safe_path(file_path)
        if full is None:
            return InvokeResult(ok=False, error="非法路径或路径越界")
        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            return InvokeResult(ok=True, data={
                "content": f"文件已写入: {file_path} ({len(content)} 字节)",
                "path": file_path,
                "size": len(content),
            })
        except Exception as e:
            return InvokeResult(ok=False, error=str(e))

    def _list(self, payload: dict[str, Any]) -> InvokeResult:
        sub_dir = payload.get("path") or payload.get("dir") or ""
        full = self._safe_path(sub_dir) if sub_dir else self._root
        if full is None:
            return InvokeResult(ok=False, error="非法路径或路径越界")
        if not full.exists():
            return InvokeResult(ok=False, error=f"目录不存在: {sub_dir}")
        files = []
        for item in sorted(full.rglob("*")):
            if item.is_file():
                rel = item.relative_to(self._root)
                size = item.stat().st_size
                files.append({"path": str(rel), "size": size})
        return InvokeResult(ok=True, data={
            "content": "\n".join(f"{f['path']} ({f['size']}B)" for f in files),
            "files": files,
            "count": len(files),
        })
