"""
AOS v5.0 — 兼容性矩阵 (Compatibility Matrix)

对标蓝图 COMPAT(兼容性矩阵)。满足蓝图节点: COMPAT。
设计原则 (严谨 + 开放 + 灵活):
  - 能力 -> 版本清单, 每条带 status(ok/deprecated/broken) 与 notes。
  - is_compatible() 做语义化版本比较 (支持 >=, ==, ~= 等约束)。
  - 可持久化到 JSON 文件, 也可仅内存使用。
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CompatMatrix:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logger.warning("Failed to load compat matrix from %s: %s", path, e)
                self._data = {}

    def register(self, capability: str, version: str, status: str = "ok",
                 notes: str = "") -> None:
        self._data.setdefault(capability, []).append(
            {"version": version, "status": status, "notes": notes}
        )
        self._persist()

    def is_compatible(self, capability: str, constraint: str = ">=0.0.0") -> bool:
        """约束示例: '>=1.2.0', '==2.0.0', '~=1.5'。任一匹配版本的 status=ok 即通过。"""
        entries = self._data.get(capability, [])
        return any(e["status"] == "ok" and self._match(e["version"], constraint) for e in entries)

    @staticmethod
    def _parse(v: str) -> List[int]:
        nums = re.findall(r"\d+", v)
        return [int(x) for x in nums[:3]] + [0] * (3 - min(3, len(nums)))

    def _match(self, version: str, constraint: str) -> bool:
        op = ">=" if constraint.startswith(">=") else \
             "==" if constraint.startswith("==") else \
             "~=" if constraint.startswith("~=") else \
             ">" if constraint.startswith(">") else "<="
        rhs = self._parse(constraint.lstrip(">=<~ "))
        lhs = self._parse(version)
        if op == "==":
            return lhs == rhs
        if op == "~=":
            return lhs[0] == rhs[0] and lhs[1] >= rhs[1]  # 兼容同主版本, 次版本不低于
        if op == ">=":
            return lhs >= rhs
        if op == ">":
            return lhs > rhs
        if op == "<=":
            return lhs <= rhs
        return lhs >= rhs

    def _persist(self) -> None:
        if self.path:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.debug("Failed to persist compat matrix to %s: %s", self.path, e)

    def snapshot(self) -> Dict[str, List[Dict[str, Any]]]:
        return json.loads(json.dumps(self._data))
