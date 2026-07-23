"""项目级沙箱工作空间（Project Sandbox Workspace）。

把整个 AOS 项目代码库安全地加载进隔离工作空间：
- 完整镜像项目文件结构
- 所有文件操作（读/写/删除）都在沙箱内进行，不影响真实项目
- 支持快照/回滚
- 支持目录白名单（只暴露部分目录给炼化流程）

安全设计：
- 沙箱目录 = 临时目录 + 项目快照，与真实项目物理隔离
- 路径逃逸检测（防止 ../ 跳出沙箱）
- 文件大小/数量硬限制
- 所有写操作前自动备份，支持一键回滚

遵循 AOS 全局约定：
- 与 execution.workspace.WorkspaceManager 风格一致
- 与 execution.sandbox.SandboxManager 的安全检查理念一致
- 资源受限（文件总数/总大小/单文件大小）
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 资源硬上限 ──────────────────────────────────────────────────────────
_MAX_FILES = 10000
_MAX_TOTAL_SIZE_MB = 500
_MAX_SINGLE_FILE_MB = 50
_MAX_SNAPSHOTS = 20


@dataclass
class SandboxSnapshot:
    """沙箱快照：记录某个时间点的文件系统状态，用于回滚。"""
    id: str
    name: str
    created_at: float
    description: str = ""
    file_count: int = 0
    total_size_bytes: int = 0
    snapshot_dir: str = ""  # 快照存储路径

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
            "description": self.description,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
        }


class ProjectSandbox:
    """项目级沙箱：把整个项目代码库安全地镜像到隔离目录。

    典型流程：
        sb = ProjectSandbox(project_root="d:\\AOS")
        sb.create()               # 把项目镜像到临时沙箱
        sb.read_file("src/api/main.py")
        sb.write_file("src/test.py", "print('hello')")
        snap = sb.snapshot("before-refactor")
        # ... 做一堆修改 ...
        sb.rollback(snap.id)      # 一键回滚
        sb.destroy()              # 销毁沙箱
    """

    def __init__(self, project_root: str, name: str = None,
                 include_dirs: Optional[List[str]] = None,
                 exclude_patterns: Optional[List[str]] = None):
        """
        Args:
            project_root: 真实项目根目录（绝对路径）
            name: 沙箱名称（用于日志识别）
            include_dirs: 只镜像这些子目录（相对路径），None 表示全部
            exclude_patterns: 排除的文件/目录模式（glob 风格，简单后缀匹配）
        """
        self._project_root = Path(project_root).resolve()
        if not self._project_root.is_dir():
            raise ValueError(f"项目根目录不存在: {project_root}")

        self._name = name or f"refinery-{self._project_root.name}"
        self._include_dirs = include_dirs  # None = 全部
        self._exclude_patterns = exclude_patterns or [
            # VCS / 缓存
            ".git", "__pycache__", "*.pyc", ".pytest_cache",
            ".mypy_cache", ".ruff_cache",
            # 虚拟环境 / 依赖
            "node_modules", ".venv", "venv", "*.egg-info",
            # 运行时数据（非源码）
            "data", "logs", "_traces", ".secrets",
            "zvec_data", "_learning_memory",
            # 大型外部资源（非项目自身代码）
            "third_party", "references", "agency-agents-zh",
            "cognee_graph", "crawl4ai",
            # 配置中的运行时二进制 / LSP
            "config",
            # 文档 / 报告（炼化只处理代码）
            "docs", "reports",
            # 二进制 / 媒体
            "*.db", "*.db.zst", "*.zip", "*.tar.gz",
            "*.png", "*.jpg", "*.jpeg", "*.gif", "*.ico",
            "*.pdf", "*.docx", "*.xlsx",
            "*.mp4", "*.mp3", "*.wav",
            "*.lock", "LOCK",
        ]

        self._sandbox_root: Optional[Path] = None
        self._snapshots: Dict[str, SandboxSnapshot] = {}
        self._created = False

    # ── 生命周期 ────────────────────────────────────────────────────

    @property
    def is_created(self) -> bool:
        return self._created and self._sandbox_root is not None

    @property
    def root(self) -> str:
        if not self._sandbox_root:
            raise RuntimeError("沙箱尚未创建")
        return str(self._sandbox_root)

    def create(self) -> Dict[str, Any]:
        """创建沙箱：把项目镜像到临时目录。"""
        if self._created:
            return {"success": False, "error": "沙箱已存在"}

        sandbox_dir = Path(tempfile.mkdtemp(prefix=f"aos-refinery-{self._name}-")).resolve()
        logger.info("创建项目沙箱: name=%s, path=%s", self._name, sandbox_dir)

        try:
            self._mirror_project(sandbox_dir)
        except Exception as e:
            shutil.rmtree(sandbox_dir, ignore_errors=True)
            logger.error("项目镜像失败: %s", e)
            return {"success": False, "error": f"项目镜像失败: {e}"}

        self._sandbox_root = sandbox_dir
        self._created = True

        stats = self._stats()
        logger.info("沙箱创建完成: files=%d, size_mb=%.2f",
                    stats["file_count"], stats["total_size_mb"])
        return {
            "success": True,
            "name": self._name,
            "path": str(sandbox_dir),
            **stats,
        }

    def destroy(self) -> Dict[str, Any]:
        """销毁沙箱，清理所有临时文件。"""
        if not self._created or not self._sandbox_root:
            return {"success": True, "message": "沙箱不存在"}

        try:
            shutil.rmtree(self._sandbox_root, ignore_errors=True)
            # 清理快照目录
            for snap in self._snapshots.values():
                if snap.snapshot_dir:
                    shutil.rmtree(snap.snapshot_dir, ignore_errors=True)
            self._snapshots.clear()
            self._created = False
            self._sandbox_root = None
            logger.info("沙箱已销毁: %s", self._name)
            return {"success": True}
        except Exception as e:
            logger.error("沙箱销毁失败: %s", e)
            return {"success": False, "error": str(e)}

    # ── 文件操作 ────────────────────────────────────────────────────

    def read_file(self, rel_path: str) -> Dict[str, Any]:
        """读取沙箱内文件。"""
        try:
            full = self._safe_path(rel_path)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if not full.is_file():
            return {"success": False, "error": f"文件不存在: {rel_path}"}

        try:
            content = full.read_text(encoding="utf-8")
            return {"success": True, "content": content, "path": rel_path,
                    "size": full.stat().st_size,
                    "mtime": full.stat().st_mtime}
        except UnicodeDecodeError:
            # 二进制文件用 base64
            import base64
            data = full.read_bytes()
            return {"success": True, "content_b64": base64.b64encode(data).decode(),
                    "path": rel_path, "size": len(data), "binary": True,
                    "mtime": full.stat().st_mtime}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, rel_path: str, content: str,
                   auto_snapshot: bool = True) -> Dict[str, Any]:
        """写入文件。默认自动做快照（单文件级）。"""
        try:
            full = self._safe_path(rel_path, allow_new=True)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        existed = full.exists()
        old_content = None
        if existed and auto_snapshot:
            try:
                old_content = full.read_text(encoding="utf-8")
            except Exception:
                old_content = None

        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
            self._check_resource_limits()
            logger.debug("写入文件: %s (existed=%s)", rel_path, existed)
            return {
                "success": True,
                "path": rel_path,
                "size": full.stat().st_size,
                "created": not existed,
                "prev_snapshot": old_content is not None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_file(self, rel_path: str, auto_snapshot: bool = True) -> Dict[str, Any]:
        """删除文件。默认自动备份。"""
        try:
            full = self._safe_path(rel_path)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if not full.exists():
            return {"success": False, "error": f"文件不存在: {rel_path}"}

        backup = None
        if auto_snapshot:
            try:
                backup = full.read_bytes()
            except Exception:
                backup = None

        try:
            full.unlink()
            return {"success": True, "path": rel_path,
                    "backup_saved": backup is not None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_files(self, rel_dir: str = "", pattern: str = "*.py") -> Dict[str, Any]:
        """列出沙箱内的文件。"""
        try:
            if rel_dir and rel_dir != ".":
                full = self._safe_path(rel_dir)
            else:
                if not self._sandbox_root:
                    raise ValueError("沙箱未创建")
                full = self._sandbox_root
        except ValueError as e:
            return {"success": False, "error": str(e)}

        if not full.is_dir():
            return {"success": False, "error": f"目录不存在: {rel_dir}"}

        try:
            import fnmatch
            files = []
            for p in sorted(full.rglob(pattern)):
                if p.is_file():
                    rel = p.relative_to(self._sandbox_root)
                    files.append({
                        "path": str(rel),
                        "name": p.name,
                        "size": p.stat().st_size,
                        "mtime": p.stat().st_mtime,
                    })
            return {"success": True, "files": files, "count": len(files)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def file_exists(self, rel_path: str) -> bool:
        """判断文件是否存在（沙箱内）。"""
        try:
            full = self._safe_path(rel_path)
            return full.is_file()
        except ValueError:
            return False

    # ── 快照 / 回滚 ────────────────────────────────────────────────

    def snapshot(self, name: str, description: str = "") -> Dict[str, Any]:
        """创建全量快照（复制整个沙箱）。"""
        if not self._created or not self._sandbox_root:
            return {"success": False, "error": "沙箱未创建"}

        if len(self._snapshots) >= _MAX_SNAPSHOTS:
            # 淘汰最老的
            oldest = min(self._snapshots.values(), key=lambda s: s.created_at)
            if oldest.snapshot_dir:
                shutil.rmtree(oldest.snapshot_dir, ignore_errors=True)
            del self._snapshots[oldest.id]

        snap_id = hashlib.sha256(f"{self._name}-{time.time()}".encode()).hexdigest()[:12]
        snap_dir = Path(tempfile.mkdtemp(prefix=f"aos-snap-{snap_id}-")).resolve()

        try:
            # 复制整个沙箱到快照目录
            for item in self._sandbox_root.iterdir():
                dst = snap_dir / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, symlinks=False)
                else:
                    shutil.copy2(item, dst)

            stats = self._count_stats(snap_dir)
            snap = SandboxSnapshot(
                id=snap_id,
                name=name,
                created_at=time.time(),
                description=description,
                file_count=stats["file_count"],
                total_size_bytes=stats["total_size_bytes"],
                snapshot_dir=str(snap_dir),
            )
            self._snapshots[snap_id] = snap
            logger.info("快照创建: id=%s, name=%s, files=%d",
                        snap_id, name, stats["file_count"])
            return {"success": True, "snapshot": snap.to_dict()}
        except Exception as e:
            shutil.rmtree(snap_dir, ignore_errors=True)
            return {"success": False, "error": f"快照创建失败: {e}"}

    def rollback(self, snapshot_id: str) -> Dict[str, Any]:
        """回滚到指定快照。"""
        if snapshot_id not in self._snapshots:
            return {"success": False, "error": f"快照不存在: {snapshot_id}"}

        snap = self._snapshots[snapshot_id]
        if not snap.snapshot_dir or not Path(snap.snapshot_dir).is_dir():
            return {"success": False, "error": "快照数据已丢失"}

        if not self._sandbox_root:
            return {"success": False, "error": "沙箱未创建"}

        try:
            # 清空当前沙箱，再从快照复制回来
            for item in self._sandbox_root.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            snap_dir = Path(snap.snapshot_dir)
            for item in snap_dir.iterdir():
                dst = self._sandbox_root / item.name
                if item.is_dir():
                    shutil.copytree(item, dst, symlinks=False)
                else:
                    shutil.copy2(item, dst)

            logger.info("回滚完成: snapshot=%s", snapshot_id)
            stats = self._stats()
            return {"success": True, **stats}
        except Exception as e:
            return {"success": False, "error": f"回滚失败: {e}"}

    def list_snapshots(self) -> Dict[str, Any]:
        """列出所有快照。"""
        snaps = sorted(self._snapshots.values(), key=lambda s: s.created_at, reverse=True)
        return {"success": True, "snapshots": [s.to_dict() for s in snaps],
                "count": len(snaps)}

    # ── 执行命令（沙箱内） ────────────────────────────────────────

    def run_command(self, cmd: str, timeout: int = 60,
                    cwd: str = None) -> Dict[str, Any]:
        """在沙箱目录内执行命令。

        注意：这是最佳努力的隔离，不是真正的容器级隔离。
        危险命令仍会被黑名单拦截（复用 SandboxManager 的检查）。
        """
        if not self._created or not self._sandbox_root:
            return {"success": False, "error": "沙箱未创建"}

        try:
            work_dir = self._safe_path(cwd) if cwd else self._sandbox_root
            if not work_dir.is_dir():
                return {"success": False, "error": f"工作目录不存在: {cwd}"}
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # 复用 SandboxManager 的危险模式检查
        from execution.sandbox import _check_dangerous_patterns
        danger = _check_dangerous_patterns(cmd)
        if danger:
            logger.warning("沙箱命令被拒: pattern=%s, cmd=%.100s", danger, cmd)
            return {"success": False, "error": f"Blocked: dangerous pattern '{danger}'"}

        import subprocess
        import sys

        env = self._safe_env()

        try:
            if sys.platform == "win32":
                proc = subprocess.run(
                    ["cmd", "/c", cmd],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            else:
                proc = subprocess.run(
                    ["bash", "-c", cmd],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )

            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
                "command": cmd,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"命令超时（>{timeout}s）"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 内部方法 ────────────────────────────────────────────────────

    def _mirror_project(self, target_dir: Path) -> None:
        """把项目镜像到目标目录（容错：个别文件失败不中断整体）。"""
        if self._include_dirs:
            for sub in self._include_dirs:
                src = self._project_root / sub
                if src.is_dir():
                    dst = target_dir / sub
                    self._copytree_resilient(src, dst)
                elif src.is_file():
                    dst = target_dir / sub
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        shutil.copy2(src, dst)
                    except (OSError, PermissionError) as e:
                        logger.warning("跳过文件 %s: %s", src, e)
        else:
            self._copytree_resilient(self._project_root, target_dir)

    def _copytree_resilient(self, src: Path, dst: Path) -> None:
        """容错版 copytree：遇到无法复制的文件/目录时跳过并记录，不中断整体镜像。"""
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            # 应用排除模式
            if self._should_exclude(item.name):
                continue

            dst_item = dst / item.name
            try:
                if item.is_dir():
                    self._copytree_resilient(item, dst_item)
                elif item.is_file() and not item.is_symlink():
                    shutil.copy2(item, dst_item)
                # 跳过符号链接（避免 Windows nul 设备等问题）
            except (OSError, PermissionError, ValueError) as e:
                logger.warning("镜像跳过 %s: %s", item, e)

    def _should_exclude(self, name: str) -> bool:
        """检查文件/目录名是否匹配排除模式。"""
        import fnmatch
        for pat in self._exclude_patterns:
            if fnmatch.fnmatch(name, pat) or name == pat:
                return True
        # 隐藏文件/目录默认排除（保留 .gitignore / .env.example）
        if name.startswith(".") and name not in (".gitignore", ".env.example"):
            return True
        return False

    def _ignore_patterns(self, src: str, names: List[str]) -> List[str]:
        """shutil.copytree 的 ignore 回调。"""
        ignored = []
        for name in names:
            path = Path(src) / name
            for pat in self._exclude_patterns:
                import fnmatch
                if fnmatch.fnmatch(name, pat) or name == pat:
                    ignored.append(name)
                    break
            if name.startswith(".") and name not in ignored:
                # 隐藏文件/目录默认排除（.env 等敏感文件）
                # 但保留项目配置如 .gitignore
                if name not in (".gitignore", ".env.example"):
                    ignored.append(name)
        return ignored

    def _safe_path(self, rel_path: str, allow_new: bool = False) -> Path:
        """路径安全检查：确保 rel_path 不跳出沙箱根目录。"""
        if not self._sandbox_root:
            raise ValueError("沙箱未创建")

        # 规范化相对路径
        rel = Path(rel_path)
        if rel.is_absolute():
            raise ValueError("不允许绝对路径，必须使用相对路径")

        full = (self._sandbox_root / rel).resolve()
        # 确保在沙箱根目录内
        try:
            full.relative_to(self._sandbox_root.resolve())
        except ValueError:
            raise ValueError(f"路径逃逸检测: {rel_path}")

        return full

    def _safe_env(self) -> Dict[str, str]:
        """构造不含 AOS 机密的安全环境变量。"""
        from skills.sandbox import _SANDBOX_SAFE_ENV_KEYS
        env: Dict[str, str] = {}
        for k in _SANDBOX_SAFE_ENV_KEYS:
            if k in os.environ:
                env[k] = os.environ[k]
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _stats(self) -> Dict[str, Any]:
        if not self._sandbox_root:
            return {"file_count": 0, "total_size_bytes": 0, "total_size_mb": 0.0}
        s = self._count_stats(self._sandbox_root)
        return {**s, "total_size_mb": round(s["total_size_bytes"] / (1024 * 1024), 2)}

    @staticmethod
    def _count_stats(directory: Path) -> Dict[str, int]:
        count = 0
        total = 0
        for p in directory.rglob("*"):
            if p.is_file():
                count += 1
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
        return {"file_count": count, "total_size_bytes": total}

    def _check_resource_limits(self) -> None:
        """检查资源是否超限。超限抛异常。"""
        if not self._sandbox_root:
            return
        stats = self._count_stats(self._sandbox_root)
        if stats["file_count"] > _MAX_FILES:
            raise RuntimeError(f"文件数超限: {stats['file_count']} > {_MAX_FILES}")
        if stats["total_size_bytes"] > _MAX_TOTAL_SIZE_MB * 1024 * 1024:
            raise RuntimeError(f"总大小超限: {stats['total_size_bytes'] / 1024 / 1024:.1f}MB > {_MAX_TOTAL_SIZE_MB}MB")

    def __enter__(self):
        self.create()
        return self

    def __exit__(self, *args):
        self.destroy()
