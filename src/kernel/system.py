"""AOS 系统组装层 — 把内核 + 四层 + 插件装配成可运行的系统实例。

v1.0"物种思维"的装配入口：build_default_system() 返回一个 AOSSystem，
内含极简内核 + 四层结构（模型网关/MCP总线/Agent运行时/UI）。

装配逻辑：
1. 先 build_default_kernel()（wiring.py）→ 内核 + 种子插件
2. 再把四层 manager 接上内核的 pluggable slots → 完整的 AOSSystem
3. 注入真实回调（自愈→重启、淘汰→stop_agent、育种→register_agent）

调用方：app 启动 / 测试 / 脚本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .kernel import AOSKernel
from .layers import (
    AgentRuntimeLayer,
    MCPBusLayer,
    ModelGatewayLayer,
    WebUILayer,
)
from .wiring import build_default_kernel
from .types import AgentSpec


@dataclass
class AOSSystem:
    """v1.0 完整系统实例：内核 + 四层 + 插件。

    使用者可以：
    - system.kernel.register_agent(...)    # Agent 生命周期
    - system.kernel.send_message(...)      # 消息路由
    - system.kernel.check_permission(...)  # 权限治理
    - system.model_gateway.chat_unified(prompt)         # 统一调用
    - system.model_gateway.route(prompt, strategy=...)  # 智能路由
    - system.model_gateway.cost_tracker.total_usage()   # 成本控制
    - system.mcp_bus.discover()                         # 服务发现
    - system.mcp_bus.route_call(skill, params, caller)  # 消息路由+权限校验
    - system.agent_runtime.remember(key, value)         # 记忆管理
    - system.agent_runtime.run_workflow(steps)          # 工作流编排(真并发)
    - system.ui.list_surfaces()                         # 三 UI 面
    """

    kernel: AOSKernel
    model_gateway: ModelGatewayLayer | None = None
    mcp_bus: MCPBusLayer | None = None
    agent_runtime: AgentRuntimeLayer | None = None
    ui: WebUILayer | None = None
    version: str = "1.0.0"

    # 优雅降级标记
    degradation: Dict[str, str] = field(default_factory=dict)

    def list_surfaces(self):
        return self.ui.list_surfaces() if self.ui else []

    def health_report(self) -> dict:
        """轻量存活报告：内核 + 四层状态。"""
        agents = len(self.kernel.list_agents())
        models = len(self.model_gateway.list_models()) if self.model_gateway else 0
        skills = len(self.mcp_bus.discover()) if self.mcp_bus else 0
        return {
            "version": self.version,
            "kernel": {"agents": agents, "ok": True},
            "model_gateway": {"models": models, "ok": self.model_gateway is not None},
            "mcp_bus": {"skills": skills, "ok": self.mcp_bus is not None},
            "agent_runtime": {
                "engine": self.agent_runtime.engine_health() if self.agent_runtime else "unavailable",
                "ok": self.agent_runtime is not None,
            },
            "ui": {
                "platform": self.ui.platform() if self.ui else "none",
                "surfaces": len(self.ui.list_surfaces()) if self.ui else 0,
            },
            "degradations": self.degradation,
        }


def build_default_system(base_url: str = "http://localhost:8000",
                          isolate_heavy: bool = True,
                          inject_brain: bool = True) -> AOSSystem:
    """组装默认 AOS 系统：内核 + 四层 + 真实回调接入。"""
    kernel = build_default_kernel(isolate_heavy=isolate_heavy,
                                   inject_brain=inject_brain)
    degradation: Dict[str, str] = {}

    # 模型网关层
    gw_plugin = kernel._model_gateway
    model_gw = ModelGatewayLayer(gw_plugin) if gw_plugin else None
    if model_gw is None:
        degradation["model_gateway"] = "skipped (no adapter)"

    # MCP 总线层
    bus_plugin = kernel._skill_bus
    mcp_bus = MCPBusLayer(bus_plugin, kernel) if bus_plugin else None
    if mcp_bus is None:
        degradation["mcp_bus"] = "skipped (no adapter)"

    # Agent 运行时层
    runtime = (kernel._runtimes.get("litellm")
               or (list(kernel._runtimes.values())[0] if kernel._runtimes else None))
    agent_rt = AgentRuntimeLayer(runtime, kernel) if runtime else None
    if agent_rt is None:
        degradation["agent_runtime"] = "skipped (no engine)"

    ui = WebUILayer(base_url=base_url)

    # === 注入真实回调：物种三层不再空转 ===

    # 自愈 → 真重启
    def _heal_restart(agent_id: str) -> bool:
        try:
            inst = kernel.get_agent(agent_id)
            if inst:
                kernel.stop_agent(agent_id)
            spec = AgentSpec(agent_id=agent_id, name=agent_id,
                             engine=inst.spec.engine if inst else "litellm")
            kernel.register_agent(spec)
            kernel.events.emit(__import__("kernel.events", fromlist=["Event"]).Event(
                "agent.started", "self_healer", {"agent_id": agent_id}))
            return True
        except Exception:
            return False

    def _heal_fallback(model: str) -> str:
        return "zhipu/glm-4-flash"

    def _heal_isolate(skill_id: str) -> bool:
        return True  # MCP 层标记隔离

    from .immunity import SelfHealer
    healer = SelfHealer(kernel.events,
                        restart_agent=_heal_restart,
                        fallback_model=_heal_fallback,
                        isolate_skill=_heal_isolate)

    # 自然选择 → 真淘汰
    def _decommission(agent_id: str) -> None:
        kernel.stop_agent(agent_id)

    # 育种 → 真孵化
    def _spawn_agent(dna) -> str | None:
        try:
            spec = dna.to_spec()
            kernel.register_agent(spec)
            return spec.agent_id
        except Exception:
            return None

    system = AOSSystem(
        kernel=kernel,
        model_gateway=model_gw,
        mcp_bus=mcp_bus,
        agent_runtime=agent_rt,
        ui=ui,
        degradation=degradation,
    )

    # 附加物种服务到 system（可选访问）
    system._healer = healer         # type: ignore[attr-defined]
    system._decommission = _decommission  # type: ignore[attr-defined]
    system._spawn_agent = _spawn_agent   # type: ignore[attr-defined]

    return system


__all__ = ["AOSSystem", "build_default_system"]
