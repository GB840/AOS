"""接线层：把现有种子登记为内核插件，组装出一个可用的 AOSKernel。

这是"演化而非革命"的落地点：不改动 brain.py（1965 行单体），而是把已有的
真实能力（litellm / 四个真实 OSS / MCP）经薄适配器挂到内核 ABC 上。内核
核心零依赖；本文件才 import 具体实现，且对每个插件用 try/except 包裹，
缺依赖时跳过该插件而不影响内核存活。

调用方：app 启动 / 测试 / CLI 引导时 `from kernel.wiring import build_default_kernel`。
"""

from __future__ import annotations

from .kernel import AOSKernel
from .plugins import FabricAgentRuntime, LiteLLMModelGateway, MCPSkillBus

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


def build_default_kernel(default_grant: bool = True) -> AOSKernel:
    """组装默认内核：登记模型网关 + 四个 OSS 运行时 + MCP 技能总线。

    返回的内核已可用：register_agent / send_message / check_permission /
    list_agents / stop_agent 全部走内核合约，具体引擎都是插件。
    """
    kernel = AOSKernel()

    # 1) 模型网关：mistralrs 主（本地三端点）+ litellm 兜底（云 100+ 模型）
    #    对齐对账表"mistralrs 主、云兜底"；组合成一条网关级降级链。
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

    # 3) 技能总线：MCP 协议
    try:
        kernel.set_skill_bus(MCPSkillBus())
    except Exception as e:
        print(f"[wiring] 技能总线登记失败: {e}")

    # 4) 权限策略：默认放行（演示用）；生产应改为默认拒绝 + 显式授权。
    kernel.set_permission_policy(default_grant=default_grant)

    return kernel


__all__ = ["build_default_kernel", "AOSKernel"]
