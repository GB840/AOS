"""L1H Phy-Bus 物理适配总线 —— 完全自研核心（生命体OS 白皮书 L1H）。

作用：物理世界（传感器/执行器/眼镜/机器人）与内核之间的**唯一通道**。
它不只是消息队列，还承担生命体OS 的三条硬约束：

1. **安全联锁（Interlock）**：对物理世界不可逆的动作（actuate/reset）必须先过联锁，
   未获批准一律拒绝（对应宪法「潜在伤害永拦截」与 L7 GrowthGuard 的物理侧对应物）。
2. **背压（backpressure）**：传感器洪水时按 QoS 丢弃低优先级消息而不是拖垮内核
   —— 生命体宁可「感知降采样」也不能「心跳骤停」。
3. **可审计**：每条消息都有 seq / ts / topic / qos，异常路径留痕，不静默丢弃。

与 HAL 的分工：HAL 管「怎么下指令给设备」，Phy-Bus 管「设备与内核之间的流与安全」。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Deque, Dict, List, Optional, Tuple

# QoS：0 尽力而为（可丢） / 1 重要（尽量留） / 2 关键（永不丢，队列满则丢低优先级腾位）
QOS_BEST_EFFORT, QOS_IMPORTANT, QOS_CRITICAL = 0, 1, 2


class InterlockDenied(PermissionError):
    """安全联锁拒绝：该物理动作未获批准。"""


@dataclass
class PhyMessage:
    topic: str
    payload: dict = field(default_factory=dict)
    qos: int = QOS_BEST_EFFORT
    ts: float = field(default_factory=time.time)
    seq: int = 0
    source: str = "unknown"

    def to_dict(self) -> dict:
        return {"topic": self.topic, "payload": dict(self.payload), "qos": self.qos,
                "ts": self.ts, "seq": self.seq, "source": self.source}


class Interlock:
    """安全联锁：默认拒绝一切物理输出，显式放行的 topic 才可通过。

    放行方式二选一：
    - allow(topic)            长期放行（如已人工确认的安全动作）
    - grant_once(topic)       一次性放行（用完即焚，适合审批式操作）
    """

    #  不可逆 / 有伤害风险的 topic 前缀：永不允许长期放行，只能一次性授权
    ONESHOT_ONLY_PREFIXES: Tuple[str, ...] = ("actuator/", "power/", "reset/")

    def __init__(self, default_deny: bool = True):
        self.default_deny = default_deny
        self._allowed: set[str] = set()
        self._oneshot: Dict[str, int] = {}
        self.denied_log: List[dict] = []

    def allow(self, topic: str) -> None:
        if topic.startswith(self.ONESHOT_ONLY_PREFIXES):
            raise InterlockDenied(
                f"{topic} 属不可逆物理动作，禁止长期放行，请用 grant_once()"
            )
        self._allowed.add(topic)

    def revoke(self, topic: str) -> None:
        self._allowed.discard(topic)
        self._oneshot.pop(topic, None)

    def grant_once(self, topic: str, times: int = 1) -> None:
        self._oneshot[topic] = self._oneshot.get(topic, 0) + max(1, times)

    def check(self, topic: str) -> bool:
        if topic in self._allowed:
            return True
        left = self._oneshot.get(topic, 0)
        if left > 0:
            if left == 1:
                self._oneshot.pop(topic, None)
            else:
                self._oneshot[topic] = left - 1
            return True
        if not self.default_deny:
            return True
        self.denied_log.append({"topic": topic, "ts": time.time()})
        return False


class PhyBus:
    """带 QoS 背压与安全联锁的物理总线。"""

    def __init__(self, capacity: int = 256, interlock: Optional[Interlock] = None):
        self.capacity = capacity
        self.interlock = interlock or Interlock()
        self._q: Deque[PhyMessage] = deque()
        self._subs: Dict[str, List[Callable[[PhyMessage], None]]] = {}
        self._seq = 0
        self.dropped = 0
        self.denied = 0

    # -------------------------------------------------------------- 订阅
    def subscribe(self, topic: str, fn: Callable[[PhyMessage], None]) -> None:
        self._subs.setdefault(topic, []).append(fn)

    def unsubscribe(self, topic: str, fn: Callable[[PhyMessage], None]) -> bool:
        lst = self._subs.get(topic, [])
        if fn in lst:
            lst.remove(fn)
            return True
        return False

    # -------------------------------------------------------------- 上行
    def publish(self, topic: str, payload: Optional[dict] = None,
                qos: int = QOS_BEST_EFFORT, source: str = "unknown") -> Optional[PhyMessage]:
        """传感器→内核。队列满时按 QoS 背压：丢最低优先级的旧消息。"""
        self._seq += 1
        msg = PhyMessage(topic=topic, payload=payload or {}, qos=qos,
                         seq=self._seq, source=source)
        if len(self._q) >= self.capacity:
            if not self._evict_for(qos):
                self.dropped += 1
                return None      # 新消息本身最低优先级，直接丢，如实计数
        self._q.append(msg)
        return msg

    def _evict_for(self, incoming_qos: int) -> bool:
        """腾位：找一条 qos 严格低于新消息的最旧消息踢掉。"""
        for i, m in enumerate(self._q):
            if m.qos < incoming_qos:
                del self._q[i]
                self.dropped += 1
                return True
        return False

    # -------------------------------------------------------------- 下行
    def emit(self, topic: str, payload: Optional[dict] = None,
             source: str = "kernel") -> PhyMessage:
        """内核→物理执行器。必须过安全联锁，未授权抛 InterlockDenied。"""
        if not self.interlock.check(topic):
            self.denied += 1
            raise InterlockDenied(
                f"安全联锁拒绝物理输出 topic={topic}（需 grant_once/allow 显式授权）"
            )
        self._seq += 1
        msg = PhyMessage(topic=topic, payload=payload or {}, qos=QOS_CRITICAL,
                         seq=self._seq, source=source)
        for fn in self._subs.get(topic, []):
            fn(msg)
        return msg

    # -------------------------------------------------------------- 消费
    def drain(self, max_n: int = 64) -> List[PhyMessage]:
        """内核侧批量消费上行消息，并派发给订阅者。"""
        out: List[PhyMessage] = []
        while self._q and len(out) < max_n:
            m = self._q.popleft()
            out.append(m)
            for fn in self._subs.get(m.topic, []):
                fn(m)
        return out

    def stats(self) -> dict:
        return {"pending": len(self._q), "capacity": self.capacity,
                "dropped": self.dropped, "denied": self.denied,
                "topics": sorted(self._subs)}


__all__ = ["PhyBus", "PhyMessage", "Interlock", "InterlockDenied",
           "QOS_BEST_EFFORT", "QOS_IMPORTANT", "QOS_CRITICAL"]
