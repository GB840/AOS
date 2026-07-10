"""v1.0 MCP 总线层：服务发现 / 消息路由 / 权限校验。

这是 v1.0 物种思维中"MCP 总线层（可换协议）"的默认实现。
层级的抽象接口是 SkillBus(ABC)（定义在 ../interfaces.py）。
本层在其上叠加三个子组件：服务发现、消息路由、权限校验。

权限校验下沉到 MCP 总线层：每次 skill 调用前经内核 check_permission。
服务发现由 SkillBus.discover_skills() 提供；本层统一该入口并附加路由决策。
消息路由：决策 caller 是否有权限调用目标 skill，再转发到总线。

依赖倒置：本层依赖 SkillBus ABC + AOSKernel，不 import 任何具体协议实现。
换协议只需换传入的 bus 实例，本层逻辑不变。
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..interfaces import SkillBus
from ..kernel import AOSKernel
from ..types import SkillInfo, SkillResult, SkillSpec


class MCPBusLayer:
    """v1.0 MCP 总线层（可换协议）。

    三个子组件：
    1. 服务发现 → discover() → List[SkillInfo]
    2. 消息路由 → route_call(skill, params, caller_agent) → SkillResult
    3. 权限校验 → 每次 call 经 kernel.check_permission(caller, "call:{skill_id}")
    """

    def __init__(self, bus: SkillBus, kernel: AOSKernel) -> None:
        self._bus = bus
        self._kernel = kernel

    # ── 服务发现 ──
    def discover(self) -> List[SkillInfo]:
        """扫描已登记的 MCP 技能（与 SkillBus.discover_skills 对接）。"""
        return self._bus.discover_skills()

    def search(self, keyword: str) -> List[SkillInfo]:
        """按关键词模糊搜索技能（服务发现增强）。"""
        kw = keyword.lower()
        return [
            s for s in self._bus.discover_skills()
            if kw in s.skill_id.lower() or kw in s.description.lower()
        ]

    # ── 消息路由 + 权限校验 ──
    def route_call(self, skill_id: str, params: Dict[str, Any],
                   caller_agent_id: str) -> SkillResult:
        """MCP 总线层的消息路由入口。

        1. 权限校验：检查 caller 是否有权调用 skill
        2. 路由决策：通过权限后转发到 SkillBus.call_skill
        """
        action = f"call:{skill_id}"
        if not self._kernel.check_permission(caller_agent_id, action):
            return SkillResult(ok=False,
                               error=f"permission denied: {caller_agent_id} ← {action}")

        try:
            return self._bus.call_skill(skill_id, params)
        except Exception as exc:
            return SkillResult(ok=False, error=f"skill error ({skill_id}): {exc}")

    def can_call(self, skill_id: str, caller_agent_id: str) -> bool:
        """快速检查 caller 是否有权调用 skill（仅权限，不执行）。"""
        return self._kernel.check_permission(caller_agent_id, f"call:{skill_id}")

    # ── 技能注册（委托） ──
    def register_skill(self, skill_id: str, description: str,
                       arguments: Dict[str, Any] | None = None,
                       handler: Any = None) -> None:
        """注册一个新技能到 MCP 总线。"""
        spec = SkillSpec(
            skill_id=skill_id,
            description=description,
            arguments=arguments or {},
            handler=handler,
        )
        self._bus.register_skill(spec)

    def grant_permission(self, agent_id: str, skill_id: str) -> None:
        """显式授权：允许 agent 调用 skill（调用内核 Permission API）。

        注意：AOSKernel 的权限系统是 key=agent_id:action 的简单字典，
        此处 set_permission_policy 接受单个 Permission 列表做增量更新并不方便。
        因此本方法直接用内核内部的 _permissions 字典（因其是单线程内存架构）。
        未来内核权限系统升级（如 RBAC）时可无缝替换本段。
        """
        from ..types import Permission
        key = f"{agent_id}:call:{skill_id}"
        # 通过内核暴露的 set_permission_policy 来添加单项权限：
        # 获取当前所有权限 → 追加新权限 → 重新设置
        current = list(self._kernel._permissions.values())
        current.append(Permission(agent_id=agent_id,
                                   action=f"call:{skill_id}",
                                   granted=True))
        self._kernel.set_permission_policy(
            default_grant=self._kernel._default_grant,
            permissions=current,
        )
