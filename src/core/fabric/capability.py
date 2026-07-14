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
    # Agnes AI: OpenAI-compatible multimodal hub (text / image / video).
    # Not one of the four mandated OSS engines - a cloud media plane AOS can
    # route to by capability when configured with AGNES_API_KEY.
    "agnes": [
        Capability.LLM_GATEWAY,
        Capability.MEDIA_IMAGE,
        Capability.MEDIA_VIDEO,
    ],
}
