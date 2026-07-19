"""Open capability taxonomy for the AOS agent fabric.

AOS composes agents by CAPABILITY, not by project name. Any real
open-source engine (OpenClaw, Hermes, DeerFlow, AG2, or anything
that appears in the future) advertises the capabilities it provides; AOS
routes a task to the best live provider. This is what makes AOS
engine-agnostic and future-proof instead of welded to four projects.
"""
from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    """Canonical capabilities an agent engine may provide.

    Open by design: engines are never hard-coded; capabilities are the
    contract. Add new members as the field evolves (ACI, economy, world
    models, etc.) without touching core logic.
    """

    # Reach / access
    CHANNEL_ACCESS = "channel.access"            # reach users on 20+ chat platforms
    CHANNEL_SEND = "channel.send"                # push a message out via a channel (e.g. WeChat)
    GROUP_ORCHESTRATION = "group.orchestration"  # multi-agent swarm / group chat

    # Cognition
    SELF_IMPROVEMENT = "cognition.self_improve"  # learns & rewrites its own skills
    LONG_HORIZON = "cognition.long_horizon"      # multi-hour autonomous execution
    PLANNING = "cognition.planning"
    REASONING = "cognition.reasoning"

    # Inference plane (the "fuel" the behaviour engines run on)
    LLM_GATEWAY = "inference.llm"              # unified LLM access via LiteLLM
    # LNN 轻量动态推理平面（时间序列 / 连续时间动态建模）。与 inference.llm
    # 正交：LLM 擅长语言/推理，LNN 擅长低维时间序列与自适应控制（参数高效、
    # 边缘友好）。AOS「高低搭配」——简单/长序列/预测类任务优先 LNN。
    INFERENCE_LNN = "inference.lnn"            # liquid neural network (CfC/LTC) 时间序列推理

    # Code understanding (codebase-memory-mcp: real stdio MCP server, tree-sitter
    # knowledge graph over the codebase — see third_party/codebase-memory-mcp/)
    CODE_UNDERSTANDING = "code.understanding"  # index / search / trace / architecture

    # Multimodal generation (Agnes AI / OpenAI-compatible media planes)
    MEDIA_IMAGE = "media.image"                # text-to-image / image-to-image
    MEDIA_VIDEO = "media.video"                # text-to-video / image-to-video (async)
    MEDIA_3D = "media.3d"                      # interactive 3D scene/app (Three.js, browser-runtime)

    # Memory
    MEMORY_PERSISTENT = "memory.persistent"
    MEMORY_EPISODIC = "memory.episodic"
    MEMORY_SEMANTIC = "memory.semantic"
    MEMORY_KNOWLEDGE = "memory.knowledge"   # RAG / Graph-RAG knowledge hub

    # Action
    CODE_EXECUTION = "action.code_exec"
    # 多智能体代码团队（code_team 芯粒）：自然语言需求 → 多文件代码
    # （架构/编码/质量门/隔离真实测试）。与 CODE_EXECUTION（只跑给定代码）
    # 正交：前者「生成」代码，后者「执行」代码。
    CODE_GENERATE = "code.generate"
    FILE_ACCESS = "action.file_access"           # read/write/list files in workspace
    ACI = "action.aci"                           # agent computer interface: hands on the machine
    TOOL_USE = "action.tool_use"

    # Search (key-free web search plane, e.g. DuckDuckGo / ddgs)
    WEB_SEARCH = "web.search"
    WEB_FETCH = "web.fetch"  # fetch & extract content from a URL

    # Voice I/O (方案三：语音作为内核的一个可替换芯粒，而非独立助手)
    # 引擎无关：whisper.cpp / faster-whisper / Web Speech API 都可服务 STT；
    # edge-tts / kokoro / XTTS / Web Speech API 都可服务 TTS。health() 如实
    # 反映引擎是否真可用，缺失则优雅降级（浏览器 Web Speech 永远兜底）。
    VOICE_STT = "voice.stt"   # 语音识别：音频 -> 文本
    VOICE_TTS = "voice.tts"   # 语音合成：文本 -> 音频
    # 原生全双工全模态（MiniCPM-o 4.5 等端到端 Omni 模型）：持续双向流，
    # 听/说/看 不阻塞、无需 VAD。与 VOICE_STT/VOICE_TTS（轮次制、积木式拼装
    # 不同引擎）正交——VOICE_OMNI 由单一 Omni 模型端到端产出「文本+语音+视觉」
    # 流，对应 fabric 的实时会话范式（open_realtime_session）。
    VOICE_OMNI = "voice.omni"  # 全双工全模态实时交互（音频/视频/文本持续流）

    # Vision / multimodal understanding (VLM 作为 AOS 的「眼睛」平面)
    # 让工作流能读截图 / 文档 / 界面元素，补全 AOS 原本「盲」的文本-only 能力。
    # 引擎无关：云端视觉 API（OpenAI 兼容 /v1/chat/completions 带 image_url）或
    # 本地 ollama MiniCPM-V-2 都可服务；无 GPU 时默认云端，本地留作未来/兜底。
    VISION_UNDERSTAND = "vision.understand"  # 图像/截图理解：图 -> 文本描述/问答

    # Data layer (structured external datasets, e.g. ExploreYC YC/a16z portfolio)
    DATA_QUERY = "data.query"

    # System / meta
    SAFETY = "system.safety"
    OBSERVABILITY = "system.observability"
    EVOLUTION_GOVERNANCE = "system.evolution"    # coordinates & safely governs other agents
    ECONOMY = "system.economy"                   # agent capability marketplace / exchange

    # Probe-only: synthetic task used by scripts/ipc_probe.py to measure the
    # kernel<->die IPC hop overhead (Day 8-10 gate). Not advertised by any
    # real engine, so route() isolates it to the benchmark adapter.
    BENCH_PING = "bench.ping"
    BENCH_ISOLATE = "bench.isolate"    # 崩溃隔离专用合成能力（tests + gate_check）
    WORKFLOW_EXECUTE = "system.workflow"  # 编排芯粒：把多芯粒串成流水线（Day15-21）
    CONTENT_PRODUCE = "content.produce"   # 自主内容生产流水线（检索→分析→剧本→导演→工具→审核→发布）

    # 内容飞轮细分能力（与 CONTENT_PRODUCE 端到端大流水线正交）：把发布后环节单独
    # 广播出来，便于路由到 echo/cast/refine/content_marketer 等专门化适配器。
    # 9 个成员与 echo_adapter/cast_adapter/refine_adapter/content_marketer_adapter
    # 的 advertise_capabilities() 字符串值一一对应（保持下游字符串匹配零破坏）。
    CONTENT_FEEDBACK = "content.feedback"         # 全网回声采集：搜索讨论→抓取→情感→需求
    CONTENT_SENTIMENT = "content.sentiment"       # 情感分析（positive/negative/neutral）
    CONTENT_NEED_MINING = "content.need_mining"   # 从反馈中挖掘潜在需求 / 问题
    CONTENT_PUBLISH = "content.publish"           # 生成发布包 / 平台发布
    CONTENT_DISTRIBUTE = "content.distribute"     # 多平台格式适配 / 分发策略
    CONTENT_OPTIMIZE = "content.optimize"         # 基于反馈的内容迭代优化建议
    CONTENT_REFINE = "content.refine"             # 局部润色 / 重新生成
    CONTENT_AB_TEST = "content.ab_test"           # A/B 测试设计与结论
    CONTENT_MARKETING_VIDEO = "content.marketing_video"  # 一句话目标→营销视频生产（端到端）
    # 防御型本地漏洞自查（只读、仅本机；仅用公开 CVE 元数据，绝不携带/运行 exploit）。
    # 把「exploitarium 式零日情报」转化为对**自己环境**的巡检能力，而非攻击能力。
    SECURITY_AUDIT = "security.audit"
    # 逆向工程（经本机 IDA Pro MCP server；仅分析你有权分析的二进制，localhost-only）。
    # 把 mrexodia/ida-pro-mcp 这类真实开源逆向工具弄进 AOS 供给面，落实「万物为我所用」。
    RE_IDA = "re.ida"


# ============================================================================
# 全局高中低三级档位（动态路由第一维度，正交于 ROUTE_STRATEGY）
# - 高(high)   : 本地重算力 / 零成本 / 最强隐私（本地优先）
# - 中(medium) : 云端优质（质量高，但有成本/依赖网络）
# - 低(low)    : 轻量兜底（免费 / 最小依赖，质量一般）
# - auto(默认) : 运行时从最高档向低档级联（高→中→低），即「云端用不了就本地」
# 引擎档位是「数据而非架构」——自由编辑 ENGINE_TIER 即可重新分级，不动路由代码。
# ============================================================================
TIER_HIGH = "high"
TIER_MEDIUM = "medium"
TIER_LOW = "low"
TIER_AUTO = "auto"
# 档位权重：越小越优先（用于排序与级联起点）
TIER_RANK: dict[str, int] = {TIER_HIGH: 0, TIER_MEDIUM: 1, TIER_LOW: 2}


# Declarative, swappable map: the four mandated real-OSS engines -> capabilities
# they are known to provide. EDIT / EXTEND FREELY. This is data, not architecture.
# "ag2" (MIT, pip `ag2`) is the real-OSS group.orchestration engine AOS
# actually runs (in-process group chat, no Docker needed). The registry is
# health-gated, so only live engines are routed.
ENGINE_CAPABILITY_MAP: dict[str, list[Capability]] = {
    "openclaw": [Capability.CHANNEL_ACCESS, Capability.CHANNEL_SEND],
    "ag2": [Capability.GROUP_ORCHESTRATION, Capability.PLANNING],
    "hermes": [
        Capability.SELF_IMPROVEMENT,
        Capability.CODE_EXECUTION,
        Capability.MEMORY_PERSISTENT,
        Capability.REASONING,
    ],
    "deerflow": [
        Capability.LONG_HORIZON,
        Capability.PLANNING,
        Capability.CODE_EXECUTION,
        Capability.MEMORY_SEMANTIC,
    ],
    # code_team 多智能体代码团队：NL→多文件代码（架构/编码/质量门/真实测试）。
    # 本地 heuristic 生成（零依赖/零成本），真实 LLM 由 AOS_CODETEAM_LLM=1 开启。
    "code-team": [Capability.CODE_GENERATE],
    # Agnes AI: OpenAI-compatible multimodal hub (text / image / video).
    # Not one of the four mandated OSS engines - a cloud media plane AOS can
    # route to by capability when configured with AGNES_API_KEY.
    "agnes": [
        Capability.LLM_GATEWAY,
        Capability.MEDIA_IMAGE,
        Capability.MEDIA_VIDEO,
    ],
    # VLM 视觉理解平面：云端视觉 API 或本地 ollama MiniCPM-V-2（无 GPU 时走云端）
    "vlm": [Capability.VISION_UNDERSTAND],
    # ComfyUI：本地节点式视觉生产引擎（文生图/图生视频/风格迁移/视频生视频）。
    # 本地服务、零成本、最强隐私 → 比云端 agnes 更贴「本地优先」；route 级联时
    # 云端用不了就回本地 ComfyUI（万物为我所用）。
    "comfyui": [Capability.MEDIA_IMAGE, Capability.MEDIA_VIDEO],
    # 内容生产导演：一句话目标 → 自主跑完整条内容生产链路（复用 hub 路由，
    # 本地优先/零成本；审核为 human-in-the-loop 停点，approve 才发布）。
    "content-director": [Capability.CONTENT_PRODUCE],
    # security-audit：防御型本地漏洞自查（仅本机、只读、用公开 CVE 元数据）
    "security-audit": [Capability.SECURITY_AUDIT],
    # ida-pro-mcp：本机 IDA Pro 逆向工程 MCP server（localhost-only，仅分析有权分析的二进制）
    "ida-pro-mcp": [Capability.RE_IDA],
}

# 引擎档位声明（数据，非架构；自由编辑）。高=本地重算力/零成本/最强隐私，
# 中=云端优质，低=轻量兜底。某能力可被哪些档位满足＝「能力分级」的静态视图，
# 由 capability_tiers() 据 ENGINE_TIER × ENGINE_CAPABILITY_MAP 推导。
ENGINE_TIER: dict[str, str] = {
    # 高：本地重算力 / 零成本 / 最强隐私
    "ag2": TIER_HIGH,            # 本地规划推理
    "mem0": TIER_HIGH,           # 本地零成本记忆（AOS_MEM0_LOCAL=1）
    "code-exec": TIER_HIGH,      # 本地 subprocess 隔离
    "code-team": TIER_HIGH,      # 本地 heuristic 生成 + 隔离执行（零成本/最强隐私）
    "file-io": TIER_HIGH,        # 本地文件读写
    # 中：云端优质（质量高，有成本/依赖网络）
    "openclaw": TIER_MEDIUM,     # 云端 LLM 网关
    "agnes": TIER_MEDIUM,        # 云端多模态
    "litellm": TIER_MEDIUM,      # 云端模型网关
    "hermes": TIER_MEDIUM,
    "deerflow": TIER_MEDIUM,
    "browser-use": TIER_MEDIUM,     # 云端浏览器自动化（依赖 browser-use + LLM）
    "langfuse": TIER_MEDIUM,
    # 低：轻量兜底（免费 / 最小依赖）
    "web-search": TIER_LOW,      # 含免费搜索源（兜底，质量一般）
    "web-fetch": TIER_LOW,
    # minicpm_o 由适配器实例按配置返回自身档位（覆盖此默认）
    "minicpm_o": TIER_MEDIUM,
    # vlm：视觉理解平面。无 GPU 时默认云端（中档），本地 ollama 为未来/兜底（高档零成本）
    "vlm": TIER_MEDIUM,
    # comfyui：本地视觉生产服务，零成本/最强隐私 → 高档（比云端 agnes 优先）
    "comfyui": TIER_HIGH,
    # content-director：本地编排（复用 hub 路由，零成本）→ 高档
    "content-director": TIER_HIGH,
    # security-audit：本地只读漏洞自查（零成本/最强隐私/纯防御）→ 高档
    "security-audit": TIER_HIGH,
    # ida-pro-mcp：本机 IDA Pro 逆向 MCP（本地优先/零成本/最强隐私）→ 高档
    "ida-pro-mcp": TIER_HIGH,
}


def capability_tiers(cap: "Capability") -> list[str]:
    """某能力可被哪些档位满足（静态「能力分级」视图）。

    基于 ENGINE_TIER × ENGINE_CAPABILITY_MAP 推导：凡能服务该能力的引擎，
    其档位集合即为该能力的可达档位（高/中/低）。调用方据此可请求特定档位，
    或按「能力分级」做 UI/降级展示。
    """
    tiers = {
        ENGINE_TIER.get(eid, TIER_MEDIUM)
        for eid, caps in ENGINE_CAPABILITY_MAP.items()
        if cap in caps
    }
    return [t for t in (TIER_HIGH, TIER_MEDIUM, TIER_LOW) if t in tiers]
