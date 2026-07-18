"""AOS 极简内核 — 只做三件事，零依赖。

v1.0 物种思维的内核契约（恒定不变）：
1. Agent 生命周期管理：register_agent / list_agents / stop_agent
2. 消息路由：send_message（在 Agent / 运行时插件之间路由）
3. 权限治理：check_permission（验证每个操作的权限）

内核本身零依赖：本文件只 import 标准库 + 同包的 .types / .interfaces。
绝不 import brain / litellm / mcp / fabric —— 那些是"插件"，由外部接线层登记进来。

具体引擎（四个真实 OSS / litellm / MCP）通过三个 ABC 插件接口挂入，
内核只持有接口引用，不持有具体实现。这就是"依赖倒置"。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .interfaces import AgentRuntime, ModelGateway, SkillBus
from .types import (
    AgentInstance,
    AgentSpec,
    AgentStatus,
    Message,
    Permission,
    Response,
)


class AOSKernel:
    """极简内核：生命周期 + 路由 + 权限。恒定不变。"""

    def __init__(self, event_bus=None) -> None:
        # 内核级注册表（进程内，内存）—— 这是内核"自己的"状态，极少量。
        self._agents: Dict[str, AgentInstance] = {}

        # 插件插槽：由外部接线层登记具体实现。内核只认接口不认实现。
        self._runtimes: Dict[str, AgentRuntime] = {}      # engine -> AgentRuntime
        self._model_gateway: Optional[ModelGateway] = None
        self._skill_bus: Optional[SkillBus] = None

        # 权限策略：默认"显式授权才放行"。可整体替换（如接 api/security.py）。
        self._permissions: Dict[str, Permission] = {}
        self._default_grant: bool = False  # 默认拒绝，需显式授权

        # 路由钩子（可选）：send_message 可经它分发到指定 runtime
        self._route_hook: Optional[Callable[[Message], Optional[str]]] = None

        # fabric 能力枢纽（可选，由接线层经 set_fabric_hub 登记）。
        # 内核核心零依赖，故此处只持引用、绝不 import 具体实现。
        self.fabric_hub: Optional[Any] = None

        # 事件总线（可选）：注入后内核在关键路径发射事件
        if event_bus is not None:
            self.events = event_bus
        else:
            from .events import EventBus
            self.events = EventBus()

    # ------------------------------------------------------------------
    # 插件登记（接线层调用，不在内核里 hardcode 任何实现）
    # ------------------------------------------------------------------
    def register_runtime(self, engine: str, runtime: AgentRuntime) -> None:
        self._runtimes[engine] = runtime

    def set_model_gateway(self, gateway: ModelGateway) -> None:
        self._model_gateway = gateway

    def set_skill_bus(self, bus: SkillBus) -> None:
        self._skill_bus = bus

    def set_route_hook(self, hook: Callable[[Message], Optional[str]]) -> None:
        """覆盖默认路由：返回 message 应送达的 agent_id / engine。"""
        self._route_hook = hook

    def set_permission_policy(self, default_grant: bool,
                              permissions: Optional[List[Permission]] = None) -> None:
        self._default_grant = default_grant
        self._permissions.clear()

    # ------------------------------------------------------------------
    # fabric 能力枢纽（可选集成；内核零依赖，只持引用 + 委派）
    # ------------------------------------------------------------------
    def set_fabric_hub(self, hub: Any) -> None:
        """登记 fabric 能力枢纽（由接线层构造并注入）。"""
        self.fabric_hub = hub

    def resolve_engine(self, capability: str) -> Optional[str]:
        """能力→引擎 单一可信源（内核级）。无枢纽或未通电返回 None。"""
        hub = self.fabric_hub
        if hub is None:
            return None
        return hub.resolve_engine(capability)

    def fabric_health(self) -> Optional[dict]:
        """返回 fabric 通电自检；未登记枢纽返回 None。"""
        hub = self.fabric_hub
        return hub.health_report() if hub is not None else None

    def grant_permission(self, agent_id: str, action: str, granted: bool = True) -> None:
        """增量授权：在保留现有策略的前提下，为单个 agent:action 设权。

        区别于 set_permission_policy（会清空全部显式授权），本方法用于
        运行时按需放行（如 v5_bridge.chat 为会话 agent 授予 receive 权限），
        配合默认拒绝实现零信任：默认锁死，仅显式授予者放行。
        """
        self._permissions[f"{agent_id}:{action}"] = Permission(
            agent_id=agent_id, action=action, granted=granted
        )

    # ------------------------------------------------------------------
    # 职责 1：Agent 生命周期
    # ------------------------------------------------------------------
    def register_agent(self, spec: AgentSpec) -> AgentInstance:
        if spec.engine not in self._runtimes:
            # 修复 P1-3：原为静默 pass（只检测不处理），导致后续 dispatch 才报错
            # 难定位。改为抛 ValueError，让调用方立即知道引擎未注册。
            raise ValueError(
                f"engine '{spec.engine}' not registered; "
                f"available: {list(self._runtimes)}"
            )
        instance = AgentInstance(agent_id=spec.agent_id, spec=spec,
                                 status=AgentStatus.PENDING)
        self._agents[spec.agent_id] = instance
        self.events.emit(self._ev("agent.registered",
                                   {"agent_id": spec.agent_id, "engine": spec.engine}))
        return instance

    def list_agents(self) -> List[AgentInstance]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[AgentInstance]:
        return self._agents.get(agent_id)

    def stop_agent(self, agent_id: str) -> None:
        inst = self._agents.get(agent_id)
        if inst is not None:
            inst.status = AgentStatus.STOPPED
            inst.updated_at = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat()
            self.events.emit(self._ev("agent.stopped",
                                       {"agent_id": agent_id,
                                        "engine": inst.spec.engine}))

    # ------------------------------------------------------------------
    # 职责 3：权限治理
    # ------------------------------------------------------------------
    def check_permission(self, agent_id: str, action: str) -> bool:
        key = f"{agent_id}:{action}"
        explicit = self._permissions.get(key)
        if explicit is not None:
            return explicit.granted
        return self._default_grant

    # ------------------------------------------------------------------
    # 职责 2：消息路由
    # ------------------------------------------------------------------
    def send_message(self, message: Message) -> Response:
        recipient = message.recipient

        # 1) 权限：内核第三职责 —— 任何操作都先过权限。
        if not self.check_permission(recipient, "receive"):
            self.events.emit(self._ev("message.denied",
                                       {"recipient": recipient,
                                        "sender": message.sender}))
            return Response(ok=False, error=f"permission denied: {recipient} <- receive")

        # 2) 路由解析：默认按 recipient 找 agent；可经 route_hook 改写。
        target_engine = None
        if self._route_hook is not None:
            target_engine = self._route_hook(message)
        if target_engine is None:
            inst = self._agents.get(recipient)
            if inst is None:
                return Response(ok=False, error=f"unknown agent: {recipient}")
            target_engine = inst.spec.engine

        runtime = self._runtimes.get(target_engine)
        if runtime is None:
            return Response(ok=False, error=f"no runtime registered for engine: {target_engine}")

        # 3) 分发到具体运行时插件（内核不实现，只路由）。
        try:
            result = runtime.run_agent(
                self._agents.get(recipient, AgentInstance(
                    agent_id=recipient,
                    spec=AgentSpec(agent_id=recipient, name=recipient, engine=target_engine),
                )),
                task=message.payload,
            )
            self.events.emit(self._ev("message.routed",
                                       {"sender": message.sender,
                                        "recipient": recipient,
                                        "engine": target_engine,
                                        "ok": result.ok}))
            return result
        except Exception as e:  # 运行时插件故障不影响内核存活
            self.events.emit(self._ev("message.routed",
                                       {"sender": message.sender,
                                        "recipient": recipient, "error": str(e)}))
            return Response(ok=False, error=f"runtime error ({target_engine}): {e}")

    def _ev(self, event_type: str, payload: dict):
        from .events import Event
        return Event(event_type=event_type, source="kernel", payload=payload)
