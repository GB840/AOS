"""子智能体 / 部门角色注册逻辑 —— 从 UnifiedBrain 抽出的独立模块。

这是 #101 (brain.py 渐进式拆分) 的第一步: 把 self-contained 的注册逻辑
从 1300+ 行的 core/brain.py 搬到此处, brain.py 仅保留薄委派包装, 仍作为
合法集成层总枢纽 (不强制退役, 见工作记忆铁律校正)。

注册逻辑只依赖 brain 的几个属性 (subagents / deerflow / skill_registry /
mcp) 与 config, 不触碰内部私有方法, 故可安全外移且不破冷启动。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_subagents(brain, cfg) -> None:
    """注册全部子智能体到 SubAgentRegistry 与 DeerFlow handler。

    OpenClaw 不再由自研 OpenClawSubAgent 注册 (DEPRECATED, 违反"用真实开源"
    铁律, 且其 detect_openclaw_path 实际返回 None 桥接悬空)。OpenClaw 统一由
    Fabric OpenClawAdapter 经真实部署的 OpenClaw Gateway(:18789) 服务。
    """
    if getattr(cfg, "OPENCLAW_ENABLED", False):
        logger.info(
            "OpenClaw 由 Fabric OpenClawAdapter (真实 Gateway) 提供服务, "
            "跳过自研 OpenClawSubAgent 注册"
        )

    try:
        if getattr(cfg, "UITARS_ENABLED", False):
            from subagents import UITarsSubAgent

            ut = UITarsSubAgent(
                use_mcp=getattr(cfg, "UITARS_USE_MCP", False),
                mcp_port=getattr(cfg, "UITARS_MCP_PORT", 8090),
            )
            brain.subagents.register("uitars", ut.DESCRIPTION, ut.CAPABILITIES, ut.handle)
            brain.deerflow.register_handler("gui_automation", ut.handle)
            logger.info("UI-TARS subagent registered")
    except Exception as e:
        logger.warning("UI-TARS subagent unavailable: %s", e)

    try:
        if getattr(cfg, "LOBSTER_ENABLED", False):
            from subagents import LobsterSubAgent

            lb = LobsterSubAgent(
                mode=getattr(cfg, "LOBSTER_MODE", "openclaw_bridge"),
                openclaw_command=getattr(cfg, "OPENCLAW_COMMAND", "npx"),
                lobster_port=getattr(cfg, "LOBSTER_PORT", 8091),
            )
            brain.subagents.register("lobster", lb.DESCRIPTION, lb.CAPABILITIES, lb.handle)
            brain.deerflow.register_handler("office_automation", lb.handle)
            logger.info("Lobster subagent registered")
    except Exception as e:
        logger.warning("Lobster subagent unavailable: %s", e)

    try:
        from subagents.vimax_agent import ViMaxSubagent

        vm = ViMaxSubagent()
        brain.subagents.register("vimax", vm.DESCRIPTION, vm.CAPABILITIES, vm.handle)
        brain.deerflow.register_handler("video_generation", vm.handle)
        logger.info("ViMax subagent registered")
    except Exception as e:
        logger.warning("ViMax subagent unavailable: %s", e)

    try:
        from subagents.ima_agent import IMASubagent

        ima = IMASubagent()
        brain.subagents.register("ima", ima.DESCRIPTION, ima.CAPABILITIES, ima.handle)
        brain.deerflow.register_handler("knowledge_search", ima.handle)
        logger.info("IMA subagent registered")
    except Exception as e:
        logger.warning("IMA subagent unavailable: %s", e)

    try:
        from subagents.ruflo_agent import RuFloSubagent

        rf = RuFloSubagent()
        brain.subagents.register("ruflo", rf.DESCRIPTION, rf.CAPABILITIES, rf.handle)
        brain.deerflow.register_handler("code_execution", rf.handle)
        logger.info("RuFlo subagent registered")
    except Exception as e:
        logger.warning("RuFlo subagent unavailable: %s", e)

    try:
        from subagents.pixelle_agent import PixelleVideoSubagent

        px = PixelleVideoSubagent()
        brain.subagents.register(
            "pixelle_video", px.DESCRIPTION, px.CAPABILITIES, px.handle
        )
        brain.deerflow.register_handler("short_video_generation", px.handle)
        logger.info("Pixelle-Video subagent registered")
    except Exception as e:
        logger.warning("Pixelle-Video subagent unavailable: %s", e)

    try:
        from subagents.loop_engineering_agent import LoopEngineeringSubagent

        le = LoopEngineeringSubagent()
        brain.subagents.register(
            "loop_engineering", le.DESCRIPTION, le.CAPABILITIES, le.handle
        )
        brain.deerflow.register_handler("loop_engineering", le.handle)
        logger.info("Loop Engineering subagent registered")
    except Exception as e:
        logger.warning("Loop Engineering subagent unavailable: %s", e)

    try:
        from subagents.skill_agent import register_skill_as_subagent

        skill_subagents = [
            "jina_reader", "codebase_memory", "codebase_memory_mcp", "searxng",
            "lightrag", "viitor_voice", "zvec", "llama_cpp", "comfyui",
            "agency_agents", "omni_route", "open_montage", "video_use", "cognee",
            "herdr", "design_md", "no_mistakes", "lingbot_map",
        ]
        for skill_name in skill_subagents:
            register_skill_as_subagent(skill_name, brain.skill_registry, brain.subagents)
        logger.info(f"技能子智能体注册完成: {skill_subagents}")
    except Exception as e:
        logger.warning(f"技能子智能体注册失败: {e}")

    brain.mcp.set_subagent_registry(brain.subagents)


def register_agency_roles(brain) -> None:
    """注册部门角色技能"""
    try:
        from skills.agency_roles import register_agency_roles as _register

        _register()
        logger.info("Agency Roles skills registered")
    except Exception as e:
        logger.warning(f"Agency Roles registration failed: {e}")
