"""Agency Roles → Kernel 收口桥（feature flag 驱动，零侵入）
============================================================

背景
----
271 个部门角色技能目前各自在 ``execute()`` 里 ``from core import get_brain``
然后 ``brain.chat(...)``，约 538 处 ``get_brain()`` 调用直接耦合到 God Object
``core/brain.py``（2013 行）。这是 Layer 2 收口的核心对象。

设计原则（不弄虚作假）
----------------------
1. **零侵入**：本模块不修改任何 271 个角色文件。收口是「统一入口」，
   角色文件需显式 opt-in 才能切换，现有行为默认完全不变。
2. **feature flag 默认关闭**：``AOS_USE_KERNEL_FOR_ROLES`` 未设时为
   ``False``，``get_agency_runtime()`` 返回 ``_LegacyRuntime``（仍走 brain）。
3. **收口路径完全绕过 God Object**：flag 开启时走 ``kernel.v5_bridge``
   （``AOSKernel`` + ``MCPSkillBus``），不 import ``core.brain``，
   因此也不会触发沙箱里的 cognee 批量删除守卫。
4. **可灰度、可回滚**：flag 关即回退，无需改代码。

角色文件 opt-in 方式（示例）
----------------------------
    from skills.agency_roles import get_agency_runtime

    def execute(self, context):
        rt = get_agency_runtime(role_id=self.NAME)
        return rt.chat(self._build_prompt(context["task"]))
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

AGENCY_KERNEL_FLAG = "AOS_USE_KERNEL_FOR_ROLES"
AGENCY_KERNEL_ROLES = "AOS_KERNEL_ROLES"  # 逗号分隔的角色白名单，留空=全部
_DEFAULT_ROLE_ID = "agency"


def is_kernel_consolidation_enabled(role_id: str = "") -> bool:
    """动态读取 feature flag（每次调用都读环境变量，便于测试与热切换）。

    默认关闭。开启值：``1 / true / yes / on``（大小写不敏感）。
    开启后若设了 ``AOS_KERNEL_ROLES`` 白名单，则仅名单内角色走内核，
    其余仍走 brain —— 用于逐角色灰度，无需回退文件。
    """
    val = os.environ.get(AGENCY_KERNEL_FLAG, "0").strip().lower()
    if val not in ("1", "true", "yes", "on"):
        return False
    allow = os.environ.get(AGENCY_KERNEL_ROLES, "").strip()
    if not allow:
        return True
    return role_id in {a.strip() for a in allow.split(",")}


def _role_agent_id(role_id: str) -> str:
    """角色 → 内核 agent_id 的命名约定，供权限/审计追踪。"""
    return f"agency:{role_id}"


class _LegacyRuntime:
    """默认路径：保持现状，经 ``get_brain()`` 取脑。

    仅作为统一入口的兼容壳；现有角色文件仍自行调用 ``get_brain``，
    本壳供 opt-in 迁移使用，不会在 flag 关闭时被主动调用到 brain。
    """

    backend = "legacy_brain"

    def __init__(self, role_id: str):
        self.role_id = role_id
        self.agent_id = _role_agent_id(role_id)

    def chat(self, message: str, model: str = "default") -> Any:
        from core import get_brain
        return get_brain().chat(message, model=model)

    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> Any:
        from core import get_brain
        brain = get_brain()
        if hasattr(brain, "call_skill"):
            return brain.call_skill(skill_id, params)
        if hasattr(brain, "hermes") and hasattr(brain.hermes, "execute_skill"):
            return brain.hermes.execute_skill(skill_id, params)
        raise RuntimeError("legacy brain 无可用 call_skill 入口")


class _KernelRuntime:
    """收口路径：经内核（V5Bridge.call_skill / chat），完全绕过 God Object。

    数据源是 ``kernel.v5_bridge.get_bridge()``，其依赖仅为 ``kernel.*``，
    不触碰 ``core.brain``，因此不会触发 cognee 守卫。
    """

    backend = "kernel"

    def __init__(self, role_id: str):
        self.role_id = role_id
        self.agent_id = _role_agent_id(role_id)

    def chat(self, message: str, model: str = "default") -> Any:
        # model 由内核 engine 默认接管；此处透传给 caller 做审计追踪。
        from kernel.v5_bridge import get_bridge
        bridge = get_bridge()
        return bridge.chat(message, caller=self.agent_id)

    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
        from kernel.v5_bridge import get_bridge
        bridge = get_bridge()
        return bridge.call_skill(skill_id, params, caller=self.agent_id)


def get_agency_runtime(role_id: str = _DEFAULT_ROLE_ID):
    """统一入口：flag 开且（无白名单或角色在白名单）→ 内核收口；否则遗留脑。

    用法见模块 docstring。角色文件替换 ``brain = get_brain()`` 为
    ``rt = get_agency_runtime(role_id=self.NAME)`` 即可在 flag 开启时收口。
    """
    if is_kernel_consolidation_enabled(role_id):
        logger.info("[agency-roles] 收口 ON: role=%s 走内核", role_id)
        return _KernelRuntime(role_id)
    return _LegacyRuntime(role_id)
