"""接线层：把现有种子登记为内核插件，组装出一个可用的 AOSKernel。

这是"演化而非革命"的落地点：不改动 brain.py（1965 行单体），而是把已有的
真实能力（litellm / 四个真实 OSS / MCP）经薄适配器挂到内核 ABC 上。内核
核心零依赖；本文件才 import 具体实现，且对每个插件用 try/except 包裹，
缺依赖时跳过该插件而不影响内核存活。

调用方：app 启动 / 测试 / CLI 引导时 `from kernel.wiring import build_default_kernel`。
"""

from __future__ import annotations

import os

from .kernel import AOSKernel
from .plugins import FabricAgentRuntime, FabricHub, LiteLLMModelGateway, MCPSkillBus

# 真实 OSS 引擎的 fabric 适配器（按铁律：AG2 / Hermes / DeerFlow / OpenClaw）。
# 当前 fabric 已落地的适配器：OpenClaw / AG2 / Mem0 / ACI-Browser / Langfuse。
# Hermes / DeerFlow 为 vendored 引擎，经其自有模块（src/hermes、src/deerflow
# + subagent bridge）集成，未来补 fabric 适配器即自动成为内核插件（见 #84）。
_OSS_ADAPTERS = {
    "openclaw": "core.fabric.adapters.openclaw_adapter:OpenClawAdapter",
    "ag2": "core.fabric.adapters.ag2_adapter:AG2Adapter",
    "mem0": "core.fabric.adapters.mem0_adapter:Mem0Adapter",
    "aci_browser": "core.fabric.adapters.aci_browser_adapter:BrowserUseAdapter",
    "langfuse": "core.fabric.adapters.observability_langfuse_adapter:LangfuseAdapter",
}


def _load_oss_adapter(spec: str):
    """按 'module:Class' 延迟导入一个 OSS 适配器，失败返回 None。"""
    module_name, _, class_name = spec.partition(":")
    try:
        import importlib
        mod = importlib.import_module(module_name)
        return getattr(mod, class_name)
    except Exception as e:  # 缺依赖 / 未实现 / 引擎未启动
        print(f"[wiring] 跳过 OSS 适配器 {spec}: {e}")
        return None


def build_default_kernel(default_grant: bool = False) -> AOSKernel:
    """组装默认内核：登记模型网关 + 四个 OSS 运行时 + MCP 技能总线。

    返回的内核已可用：register_agent / send_message / check_permission /
    list_agents / stop_agent 全部走内核合约，具体引擎都是插件。
    """
    kernel = AOSKernel()

    # 1) 模型网关：mistralrs 主（本地三端点）→ litellm 兜底（云 100+ 模型）→ cloud 最后兜底（DeepRoute）
    #    对齐对账表 L4"mistralrs → litellm → 云"三级回退链。
    gateways = []
    try:
        from .plugins.mistralrs_gateway import MistralRSModelGateway
        mrs = MistralRSModelGateway()
        if mrs.list_models():  # MISTRALRS_ENABLED 且有端点才纳入
            gateways.append(mrs)
    except Exception as e:
        print(f"[wiring] mistralrs 网关跳过: {e}")
    try:
        gateways.append(LiteLLMModelGateway())
    except Exception as e:
        print(f"[wiring] litellm 网关登记失败: {e}")
    try:
        from .plugins.cloud_gateway import CloudModelGateway
        cloud = CloudModelGateway()
        if cloud.health().healthy or cloud._client:  # 有 API Key 配置才纳入
            gateways.append(cloud)
    except Exception as e:
        print(f"[wiring] cloud 网关跳过: {e}")

    # 1.5) Agnes AI 多模态网关（仅配置了 AGNES_API_KEY 时纳入）。
    #      经 model_id "agnes/agnes-2.0-flash" 直达；缺失 key 时跳过，不影响内核。
    try:
        if os.environ.get("AGNES_API_KEY"):
            from .plugins.agnes_gateway import AgnesModelGateway
            gateways.append(AgnesModelGateway())
    except Exception as e:
        print(f"[wiring] agnes 网关登记失败: {e}")

    try:
        if len(gateways) > 1:
            from .plugins.composite_gateway import CompositeModelGateway
            kernel.set_model_gateway(CompositeModelGateway(gateways))
        elif gateways:
            kernel.set_model_gateway(gateways[0])
    except Exception as e:
        print(f"[wiring] 模型网关组合失败: {e}")

    # 2) Agent 运行时：litellm 作为一个可运行引擎 + 四个真实 OSS
    try:
        from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
        kernel.register_runtime("litellm", FabricAgentRuntime(LiteLLMAdapter()))
    except Exception as e:
        print(f"[wiring] litellm 运行时登记失败: {e}")

    for engine, spec in _OSS_ADAPTERS.items():
        cls = _load_oss_adapter(spec)
        if cls is None:
            continue
        try:
            kernel.register_runtime(engine, FabricAgentRuntime(cls()))
        except Exception as e:
            print(f"[wiring] {engine} 运行时登记失败: {e}")

    # 2.5) fabric 能力枢纽：把六个真实 OSS 适配器登记为「按能力路由」的单一可信源，
    #      并暴露诚实的通电自检（MASTER_PLAN 阶段 1.2）。内核零依赖，故仅在此接缝构造。
    try:
        hub = FabricHub()
        # 编排芯粒作为用户态芯粒注册进枢纽（非内核），复用枢纽路由层把多芯粒
        # 串成流水线（Day15-21）。内核只做路由/隔离/资源调度，编排逻辑全外置。
        hub.add_orchestrator()
        kernel.set_fabric_hub(hub)
    except Exception as e:  # noqa: BLE001
        print(f"[wiring] fabric 能力枢纽构建失败: {e}")

    # 3) 技能总线：MCP 协议 + 安全网关（白名单 + 命令注入检测）
    #    用协议真实注册的默认工具种子化白名单，使第一方可信工具默认可用；
    #    外部 MCP 服务器仍需显式 add_to_whitelist（零信任，不自动信任）。
    try:
        from .plugins.mcp_security_gateway import MCPSecurityGateway
        _inner = MCPSkillBus()
        try:
            _seed = {s.skill_id for s in _inner.discover_skills()}
        except Exception:
            _seed = None
        kernel.set_skill_bus(MCPSecurityGateway(_inner, tool_whitelist=_seed))
    except Exception as e:
        print(f"[wiring] 技能总线登记失败: {e}")

    # 4) 权限策略：默认拒绝（零信任）。已显式授权者放行；
    #    生产应配套在调用点按需 grant_permission（见 v5_bridge.chat）。
    kernel.set_permission_policy(default_grant=default_grant)

    # 5) 对账 v1.0：把内核 ModelGateway 注入 brain.py，
    #    使其 LLM 调用走统一三级回退链而非自建 LLM 逻辑。
    #    非物理删除 brain.py，而是向内核让渡模型调用权。
    _inject_kernel_into_brain(kernel)

    return kernel


def _inject_kernel_into_brain(kernel: "AOSKernel") -> None:
    """把内核 ModelGateway 注入 UnifiedBrain 单例（可选集成，失败不影响内核）。

    brain.py 保持存活，但其 LLM 回退路径优先走内核网关，
    实现"非物理删、桥接到 fabric"的对账目标。

    注意：get_brain() 会触发 UnifiedBrain 重型初始化（含 cognee 等重依赖），
    该步骤是"增强"而非"必需"。内核的可用性与 brain 注入必须解耦——
    因此任何异常（含 cognee 日志清理在某些沙箱触发的 SystemExit）都被吞掉并告警，
    内核照常构建。否则轻量内核会被重型 brain 栈拖垮（违背"内核零依赖"）。
    """
    try:
        from core import get_brain
        brain = get_brain()
    except (Exception, SystemExit) as e:  # noqa: BLE001
        print(f"[wiring] brain 注入跳过（不影响内核构建）: {e!r}")
        return
    gw = getattr(kernel, "_model_gateway", None)
    if gw is not None:
        try:
            brain._kernel_gateway = gw
        except Exception as e:  # noqa: BLE001
            print(f"[wiring] brain 网关注入跳过: {e!r}")


__all__ = ["build_default_kernel", "AOSKernel"]
