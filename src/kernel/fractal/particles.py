"""L7 分形粒子集群 · 四类粒子类型接口 —— 完全自研核心（生命体OS 白皮书 L7）。

分形自相似公理要求：每个粒子都是「完整生命体的缩微版」，
但**职能分化**——四类角色，各自权限边界不同（宪法理念 5「权限即边界」）。

| 粒子 | 职责 | 默认权限 | 可派生子体 |
|------|------|----------|-----------|
| SENSOR    | 只感知，不改世界 | 读 + 联网(只读) | 否 |
| WORKER    | 干活，产出交付物 | 读 + 写(沙箱内) | 是（受 MAX_GEN 限） |
| GUARDIAN  | 看住别人，审批/否决 | 读 + 否决权 | 否 |
| ARCHIVIST | 记忆沉淀与蒸馏 | 读 + 写(记忆区) | 否 |

关键纪律：**权限是白名单**，未列出的能力一律没有；GUARDIAN 不能自己干活（防既当运动员又当裁判）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional

SENSOR = "sensor"
WORKER = "worker"
GUARDIAN = "guardian"
ARCHIVIST = "archivist"

ALL_TYPES: tuple[str, ...] = (SENSOR, WORKER, GUARDIAN, ARCHIVIST)

# 能力原子
CAP_READ = "read"
CAP_WRITE = "write"
CAP_NET = "net"
CAP_NET_READONLY = "net_readonly"
CAP_SPEND = "spend"
CAP_SPAWN = "spawn"
CAP_VETO = "veto"
CAP_MEMORY_WRITE = "memory_write"


@dataclass(frozen=True)
class ParticleType:
    """粒子类型定义：职责 + 白名单能力 + 是否可再分形。"""

    name: str
    duty: str
    caps: FrozenSet[str]
    can_spawn: bool = False
    max_children: int = 0

    def allows(self, cap: str) -> bool:
        return cap in self.caps


TYPES: Dict[str, ParticleType] = {
    SENSOR: ParticleType(
        SENSOR, "只感知不改世界：采集、检索、观测",
        frozenset({CAP_READ, CAP_NET_READONLY}), can_spawn=False),
    WORKER: ParticleType(
        WORKER, "执行任务并产出真实交付物",
        frozenset({CAP_READ, CAP_WRITE, CAP_NET, CAP_SPAWN}),
        can_spawn=True, max_children=8),
    GUARDIAN: ParticleType(
        GUARDIAN, "审查与否决：安全、伦理、预算守门",
        frozenset({CAP_READ, CAP_VETO}), can_spawn=False),
    ARCHIVIST: ParticleType(
        ARCHIVIST, "记忆沉淀、蒸馏、年轮归档",
        frozenset({CAP_READ, CAP_MEMORY_WRITE}), can_spawn=False),
}


@dataclass
class ParticleSpec:
    """一个具体粒子实例的规格。"""

    pid: str
    ptype: str
    generation: int = 0
    goal: str = ""
    quota: Dict[str, float] = field(default_factory=dict)
    parent: Optional[str] = None

    def __post_init__(self) -> None:
        if self.ptype not in TYPES:
            raise ValueError(f"未知粒子类型 {self.ptype!r}，合法={ALL_TYPES}")

    @property
    def type_def(self) -> ParticleType:
        return TYPES[self.ptype]

    def can(self, cap: str) -> bool:
        return self.type_def.allows(cap)

    def to_dict(self) -> dict:
        return {"pid": self.pid, "ptype": self.ptype, "generation": self.generation,
                "goal": self.goal, "quota": dict(self.quota), "parent": self.parent,
                "caps": sorted(self.type_def.caps)}


class ParticleRegistry:
    """粒子登记处：建册、权限校验、按类型检索、销毁。"""

    def __init__(self) -> None:
        self._particles: Dict[str, ParticleSpec] = {}

    def spawn(self, pid: str, ptype: str, *, generation: int = 0,
              goal: str = "", quota: Optional[Dict[str, float]] = None,
              parent: Optional[str] = None) -> ParticleSpec:
        if pid in self._particles:
            raise ValueError(f"粒子 {pid} 已存在")
        if parent is not None:
            p = self._particles.get(parent)
            if p is None:
                raise ValueError(f"父粒子 {parent} 不存在")
            if not p.type_def.can_spawn:
                raise PermissionError(
                    f"{p.ptype} 类型粒子无派生权限（只有 WORKER 可分形）")
            kids = self.children_of(parent)
            if len(kids) >= p.type_def.max_children:
                raise PermissionError(
                    f"父粒子 {parent} 子体数已达上限 {p.type_def.max_children}")
        spec = ParticleSpec(pid=pid, ptype=ptype, generation=generation,
                            goal=goal, quota=dict(quota or {}), parent=parent)
        self._particles[pid] = spec
        return spec

    def check(self, pid: str, cap: str) -> bool:
        """权限校验：粒子有没有这个能力。不存在的粒子一律 False。"""
        p = self._particles.get(pid)
        return bool(p and p.can(cap))

    def require(self, pid: str, cap: str) -> None:
        """强校验：没权限直接抛，供调用点做硬边界。"""
        if not self.check(pid, cap):
            p = self._particles.get(pid)
            have = sorted(p.type_def.caps) if p else []
            raise PermissionError(
                f"粒子 {pid}(type={p.ptype if p else '不存在'}) 无 {cap} 权限；持有={have}")

    def get(self, pid: str) -> Optional[ParticleSpec]:
        return self._particles.get(pid)

    def of_type(self, ptype: str) -> List[ParticleSpec]:
        return [p for p in self._particles.values() if p.ptype == ptype]

    def children_of(self, pid: str) -> List[ParticleSpec]:
        return [p for p in self._particles.values() if p.parent == pid]

    def kill(self, pid: str, cascade: bool = True) -> int:
        """销毁粒子（默认级联销毁子体，避免孤儿粒子游荡）。"""
        if pid not in self._particles:
            return 0
        n = 0
        if cascade:
            for c in list(self.children_of(pid)):
                n += self.kill(c.pid, cascade=True)
        self._particles.pop(pid, None)
        return n + 1

    def census(self) -> Dict[str, int]:
        out = {t: 0 for t in ALL_TYPES}
        for p in self._particles.values():
            out[p.ptype] += 1
        return out

    def __len__(self) -> int:
        return len(self._particles)


__all__ = ["ParticleType", "ParticleSpec", "ParticleRegistry", "TYPES", "ALL_TYPES",
           "SENSOR", "WORKER", "GUARDIAN", "ARCHIVIST",
           "CAP_READ", "CAP_WRITE", "CAP_NET", "CAP_NET_READONLY",
           "CAP_SPEND", "CAP_SPAWN", "CAP_VETO", "CAP_MEMORY_WRITE"]
