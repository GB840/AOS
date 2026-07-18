"""AID 身份生成 — AOS 合规基础设施之一。

为 agent 创建可审计身份(AID = Audit IDentity)。源码重建(2026-07-19):
原 .py 丢失(仅 .pyc 残留),按 brain.py + main.py 调用点契约重建。
API:create_identity / get_identity / list_identities / get_stats,Identity.aid。
"""
from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional


# 默认身份注册表路径: data/identity/identities.json
_DEFAULT_IDENTITY_PATH = str(
    Path(__file__).resolve().parents[2] / "data" / "identity" / "identities.json"
)


class Identity:
    """AOS 身份对象 — name + capabilities + aid。"""

    def __init__(
        self,
        aid: str,
        name: str,
        capabilities: Optional[list] = None,
        created_at: Optional[float] = None,
    ):
        self.aid = aid
        self.name = name
        self.capabilities = list(capabilities or [])
        self.created_at = created_at or time.time()

    def to_dict(self) -> dict:
        return {
            "aid": self.aid,
            "name": self.name,
            "capabilities": self.capabilities,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Identity":
        return cls(
            aid=d["aid"],
            name=d.get("name", ""),
            capabilities=d.get("capabilities", []),
            created_at=d.get("created_at"),
        )


class AIDGenerator:
    """AID 生成器 + 身份注册表。"""

    def __init__(self, path: Optional[str] = None):
        self._path = path or os.environ.get("AOS_IDENTITY_PATH", _DEFAULT_IDENTITY_PATH)
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        # 内存索引(懒加载)
        self._identities: Optional[dict[str, Identity]] = None

    def _load(self) -> dict[str, Identity]:
        """从磁盘加载注册表(懒加载 + 缓存)。"""
        if self._identities is not None:
            return self._identities
        self._identities = {}
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item in data.get("identities", []):
                    ident = Identity.from_dict(item)
                    self._identities[ident.aid] = ident
            except (json.JSONDecodeError, OSError):
                pass
        return self._identities

    def _persist(self) -> None:
        """把内存注册表落盘。"""
        if self._identities is None:
            return
        data = {"identities": [i.to_dict() for i in self._identities.values()]}
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_identity(self, name: str, capabilities: list) -> Identity:
        """创建新身份并注册。aid 前缀 aos- + 24 hex 随机。"""
        with self._lock:
            registry = self._load()
            aid = f"aos-{secrets.token_hex(12)}"
            ident = Identity(aid=aid, name=name, capabilities=capabilities)
            registry[aid] = ident
            self._persist()
            return ident

    def get_identity(self, aid: str) -> Optional[Identity]:
        with self._lock:
            return self._load().get(aid)

    def list_identities(self) -> list:
        with self._lock:
            return list(self._load().values())

    def get_stats(self) -> dict:
        with self._lock:
            registry = self._load()
            return {
                "count": len(registry),
                "oldest": min(
                    (i.created_at for i in registry.values()), default=None
                ),
                "newest": max(
                    (i.created_at for i in registry.values()), default=None
                ),
            }


_generator_instance: Optional[AIDGenerator] = None
_generator_lock = threading.Lock()


def get_aid_generator() -> AIDGenerator:
    """获取全局 AIDGenerator 单例。"""
    global _generator_instance
    if _generator_instance is None:
        with _generator_lock:
            if _generator_instance is None:
                _generator_instance = AIDGenerator()
    return _generator_instance
