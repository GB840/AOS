"""内核级 fabric 能力枢纽 —— 薄适配层连接真实开源引擎的落地点。

这是 MASTER_PLAN 阶段 1.2「激活 fabric 现有适配器」的核心构件：把六个真实
OSS 适配器（OpenClaw / AG2 / LiteLLM / Mem0 / ACI-Browser / Langfuse）登记为
「按能力(Capability)路由」的能力枢纽，并暴露一个**诚实的通电自检**——

    - 哪个引擎 live、哪个 dead、缺什么依赖，全部如实返回；
    - resolve_engine() 绝不返回未通电的引擎（不假装 live）；
    - 任一适配器导入/注册失败都被单独吞掉，枢纽照常构建。

内核核心零依赖；本文件（kernel/plugins 接缝）才 import 具体实现 core.fabric。
这与本项目「依赖倒置」铁律一致：内核只认 ABC 接口，真实引擎都是插件。
"""
from __future__ import annotations

import logging
import os
import shutil
import json
import time
from pathlib import Path
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional

from core.fabric import FabricRegistry
from core.fabric.route_runtime import build_route_runtime
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult, normalize_media_data
from core.fabric.adapters import (
    AG2Adapter,
    AgnesAdapter,
    BrowserUseAdapter,
    CodeExecutionAdapter,
    FileAdapter,
    LangfuseAdapter,
    LiteLLMAdapter,
    Mem0Adapter,
    OpenClawAdapter,
    SearchAdapter,
    WebFetchAdapter,
    Crawl4AIAdapter,
    MediaGenAdapter,
    ThreejsAdapter,
    STTAdapter,
    TTSAdapter,
    LNNAdapter,
    LFMAdapter,
    ScriptsAdapter,
    MiniCPMOAdapter,
    VLMAdapter,
    VideoMakerAdapter,
    RemotionAdapter,
    SecurityAuditAdapter,
    IdaProMcpAdapter,
    Img2ThreejsAdapter,
    KnowmeshAdapter,
    MediakitAdapter,
)
from core.fabric.capability import Capability
from .zhipu_chat import zhipu_chat
from .ollama_chat import ollama_chat, ollama_available
from kernel.isolation.subprocess_iso import IsolatedEngineHost
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
from kernel.plugins.plan_bridge import heuristic_plan, parse_plan_to_steps
from kernel.evolution_distiller import EvolutionDistiller

_LOG = logging.getLogger("aos.fabric.hub")

# 会话上下文存储（进程内缓存 + 磁盘持久化）。
# key=session_id, value=[{"task": "...", "response": "..."}, ...]
# 设计：内存缓存提速热会话；磁盘 JSON 落盘让 CLI 跨进程也能记住对话。
# 每个会话最多保留最近 5 轮，避免无限增长拖慢上下文注入。
# 会话「数量」也设上限：长运行服务若放任唯一 session_id 无限累积会内存泄漏(R-4)。
# 用 OrderedDict 实现 LRU：访问/写入即移到末尾，超出上限淘汰最久未用的会话。
_SESSIONS: "OrderedDict[str, List[Dict[str, str]]]" = OrderedDict()
_SESSION_MAX_TURNS = 5
_SESSION_MAX_COUNT = 1024  # 最多缓存会话数，超出按 LRU 淘汰，防无限增长
_SESSION_DIR = Path("data/workspaces/fabric/sessions")


def _session_path(session_id: str) -> Path:
    return _SESSION_DIR / f"{session_id}.json"


def _load_session(session_id: str) -> List[Dict[str, str]]:
    """加载会话历史：先查内存缓存，没有再读磁盘。"""
    if session_id in _SESSIONS:
        _SESSIONS.move_to_end(session_id)
        return _SESSIONS[session_id]
    p = _session_path(session_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                _SESSIONS[session_id] = data
                return data
        except Exception:  # noqa: BLE001
            pass
    return []


def _save_session(session_id: str, history: List[Dict[str, str]]) -> None:
    """保存会话历史到内存和磁盘。"""
    # 限制每个会话最多保留最近5轮历史
    if len(history) > _SESSION_MAX_TURNS:
        history = history[-_SESSION_MAX_TURNS:]
    _SESSIONS[session_id] = history
    _SESSIONS.move_to_end(session_id)
    # LRU 淘汰：超出会话数上限时丢弃最久未访问的会话(R-4)
    while len(_SESSIONS) > _SESSION_MAX_COUNT:
        _SESSIONS.popitem(last=False)
    try:
        _SESSION_DIR.mkdir(parents=True, exist_ok=True)
        _session_path(session_id).write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        _LOG.warning("会话保存失败: %s", e)


def _busy_wait(seconds: float) -> None:
    """忙等指定秒数（微秒级精度）。

    仅用于 IPC 开销探测（route_sim_us>0）模拟 Named Pipe 级延迟：
    Windows 的 time.sleep() 量化粒度约 1ms，无法精确模拟 20μs，故用忙等。
    生产环境 route_sim_us 恒为 0，此函数绝不触发。
    """
    if seconds <= 0:
        return
    deadline = time.perf_counter() + seconds
    while time.perf_counter() < deadline:
        pass

# 顺序即注册顺序；新增引擎只需在此追加一行 + 在 core.fabric.adapters 落适配器。
# 过滤 None：core.fabric.adapters 包对导入失败的适配器置 None，这里剔除，
# 避免 __init__ 里 `cls()` 对 None 抛 TypeError（单适配器故障不拖垮枢纽）。
_ADAPTERS: tuple[type[BaseAgentAdapter], ...] = tuple(
    a
    for a in (
        OpenClawAdapter,
        AG2Adapter,
        LiteLLMAdapter,
        Mem0Adapter,
        BrowserUseAdapter,
        LangfuseAdapter,
        SearchAdapter,       # 免 key 真实联网搜索（DuckDuckGo / ddgs，"dgg 库"）
        WebFetchAdapter,     # URL 内容抓取（stdlib urllib，零依赖）
        Crawl4AIAdapter,     # 网页爬取转 LLM 友好 Markdown（crawl4ai，需 pip install）
        MediaGenAdapter,    # 国产文生图/文生视频（智谱 CogView-4 + CogVideoX，零依赖 urllib）
        AgnesAdapter,        # OpenAI-compatible 多模态平面：文本/图像/视频（需 AGNES_API_KEY）
        CodeExecutionAdapter,  # 本地沙箱代码执行（subprocess 隔离，零依赖）
        FileAdapter,           # 文件读写（workspace 内，路径遍历防护）
        ThreejsAdapter,       # 交互式 3D 场景生成（MEDIA_3D，浏览器端渲染）
        STTAdapter,           # 语音识别（VOICE_STT：whisper.cpp/faster-whisper/Web Speech）
        TTSAdapter,           # 语音合成（VOICE_TTS：kokoro/edge-tts/XTTS/Web Speech）
        LNNAdapter,           # 液态神经网络时间序列推理（INFERENCE_LNN，纯 numpy 自包含）
        LFMAdapter,           # LFM2 轻量 LLM 供给方（inference.llm 的「低功耗」一极，高低搭配）
        ScriptsAdapter,       # 动态脚本执行（scripts/repls/*.py 热加载）
        MiniCPMOAdapter,       # 全双工全模态（VOICE_OMNI）：MiniCPM-o 4.5 推理后端
        VLMAdapter,            # 视觉理解（VISION_UNDERSTAND）：云端视觉 API / 本地 ollama MiniCPM-V-2
        VideoMakerAdapter,     # 本地视频生成（MEDIA_VIDEO）：edge-tts + PIL + ffmpeg，零成本
        RemotionAdapter,       # 高质量数据可视化视频渲染（video.remotion）：Remotion CLI 胶水
        SecurityAuditAdapter,  # 防御型本地漏洞自查（security.audit）：只读、仅本机、用公开 CVE 元数据
        Img2ThreejsAdapter,    # 图片→程序化 Three.js 重建（media.3d.reconstruct）：vendored 纯 stdlib 脚本 + divine_eye 零 token 评分
        MediakitAdapter,       # 云端音视频后期处理（media.process）：火山引擎 mediakit-cli 胶水，opt-in（默认关闭）
        KnowmeshAdapter,       # 本地文档知识库（memory.knowledge）：知络 KnowMesh HTTP-API 胶水，零依赖、本地优先
    )
    if a is not None
)
class IsolatedAdapterProxy(BaseAgentAdapter):
    """进程内代理：让被隔离到子进程的引擎仍能参与枢纽的能力路由/自检。

    注册进 FabricRegistry 的是它（而非真实适配器实例），所以 resolve_engine /
    health_report / route 的「能力匹配」逻辑零改动即可生效；真正的 invoke 与
    health 全部委派给 IsolatedEngineHost（子进程）。这是依赖倒置的干净落点：
    内核/枢纽只认 ABC，子进程是插在接缝外的实现。
    """

    def __init__(self, engine_id: str, capabilities: list,
                 host: IsolatedEngineHost) -> None:
        self._eid = engine_id
        self._caps = capabilities
        self._host = host

    @property
    def engine_id(self) -> str:
        return self._eid

    def advertise_capabilities(self) -> list:
        return list(self._caps)

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        # req.capability 是字符串（FabricHub.route 以字符串构造 InvokeRequest），
        # 子进程 worker 内部再转回 Capability 枚举，故此处直接透传字符串。
        resp = self._host.invoke(req.capability, req.payload)
        if isinstance(resp, dict):
            return InvokeResult(ok=resp.get("ok", False),
                                data=resp.get("data"), error=resp.get("error"))
        return resp

    def health(self) -> bool:
        return self._host.health()


class FabricHub:
    """能力路由枢纽：按 Capability 把任务委派给 live 的真实 OSS 引擎。"""

    # 进程内默认注册集合；接线层（build_fabric_hub）据此排除待隔离引擎，
    # 避免同一引擎既进程内又隔离地双注册。
    DEFAULT_ADAPTERS = _ADAPTERS

    def __init__(self, adapters: Optional[tuple] = None,
                 distiller: Optional["EvolutionDistiller"] = None) -> None:
        # best-effort 加载仓库根 .env：让依赖远程 key 的引擎（agnes/litellm）
        # 在任何调用路径都通电。mem0 默认走本地零成本配置（不依赖 key），本步
        # 对 mem0 非必需，仅为兼容远程 key 模式。必须在注册 adapters 之前执行。
        try:
            from dotenv import load_dotenv
            from pathlib import Path
            for cand in (Path.cwd() / ".env",
                         Path(__file__).resolve().parents[3] / ".env"):
                if cand.is_file():
                    load_dotenv(cand)
                    break
        except Exception:  # noqa: BLE001 - 无 python-dotenv / 无 .env 都不致命
            pass
        # 路由预测器「接电」：注入 predictor + outcome_store，默认启用 learned 策略。
        # 真实流量经 route() 落盘后自动训练并持久化模型（越用越准）。
        # 可用 AOS_ROUTE_STRATEGY=preference 退化为静态偏好表（零影响）。
        self._registry = FabricRegistry(**build_route_runtime())
        self._failure_monitor: Optional[Any] = None  # MAST 失败监控器，下方 try 链 best-effort 接入
        self._errors: Dict[str, str] = {}
        self._missing_capability_hooks: List[Callable] = []  # 能力缺失时触发的钩子（AutoSkill 等）
        # 白盒蒸馏路由（opt-in，理念8 闭环消费端）：把 EvolutionDistiller 的
        # 沉底建议接入 route()，让不可靠引擎在运行时被排到末尾（有备选才跳过）。
        # 默认关闭；设 AOS_DISTILLER_ROUTE=1 自动加载蒸馏记忆，清 env 即退回原路由。
        self._distiller = distiller
        self._distill_drop = os.environ.get("AOS_DISTILLER_DROP") == "1"
        if self._distiller is None and os.environ.get("AOS_DISTILLER_ROUTE") == "1":
            try:
                store = (os.environ.get("AOS_DISTILLER_STORE")
                         or "data/workspaces/fabric/distill.jsonl")
                self._distiller = EvolutionDistiller(store_path=store)
            except Exception as e:  # noqa: BLE001 - 蒸馏接电失败不拖垮枢纽
                _LOG.warning("蒸馏路由接电失败(将关闭): %s", e)
                self._distiller = None
        # 已隔离进子进程的引擎：engine_id -> IsolatedEngineHost。
        # 被隔离引擎同时以 IsolatedAdapterProxy 注册进 _registry（参与路由），
        # 但 invoke/health 全部走子进程。recover() 对它们直接 respawn 子进程。
        self._isolated: Dict[str, IsolatedEngineHost] = {}
        # 隔离引擎的最近一次恢复耗时（毫秒）：recover() 时记录，供可观测。
        self._recover_ms: Dict[str, float] = {}
        # 单芯粒故障记录：engine_id -> 最近一次 invoke 失败的 perf_counter 时间戳。
        # 用于「崩溃恢复」度量（Day11-14 闸门3）：从故障检测到恢复服务的耗时。
        self._failures: Dict[str, float] = {}
        # 模拟路由层延迟（μs）：默认 0（生产零影响）。
        # 探测时由 scripts/ipc_probe.py 通过 set_route_sim_us() 打开，
        # 用于测量「内核↔芯粒」这一跳的 IPC 开销是否 ≤5%（Day8-10 闸门）。
        self.route_sim_us: float = float(os.environ.get("ROUTE_SIM_US", "0") or "0")
        for cls in (adapters if adapters is not None else _ADAPTERS):
            if cls is None:
                continue
            try:
                # mem0 默认走本地零成本配置（ollama/sentence-transformers + 本地
                # chroma），除非 AOS_MEM0_LOCAL=0 才退回远程 key 兼容模式。本机
                # 无 ollama 时构造仍成功，invoke 时优雅降级由记忆门面兜底。
                if cls is Mem0Adapter:
                    from core.fabric.adapters.mem0_adapter import build_mem0_config
                    force_local = os.environ.get("AOS_MEM0_LOCAL", "1") != "0"
                    inst = cls(config=build_mem0_config(force_local=force_local))
                else:
                    inst = cls()
                self._registry.register(inst)
            except Exception as e:  # noqa: BLE001 - 单适配器故障不拖垮枢纽
                self._errors[cls.__name__] = repr(e)
                _LOG.warning("fabric 适配器注册失败 %s: %s", cls.__name__, e)
        # 环境变量驱动的 MCP Server 自动注册：让任意支持 MCP 的外部服务
        # （AnySearch / ExploreYC / Sim / Auriko / Timbal 等）配置即接，
        # 无需改代码。AOS_MCP_SERVERS 为 JSON 数组，每项：
        #   {"url": "...", "engine_id": "mcp-xxx",
        #    "capability_map": {"tool_name": "data.query"},  # 可选
        #    "auth_token": "..."}                              # 可选
        self._register_env_mcp_servers()
        # 腾讯开源 WeKnora 知识引擎：经其 MCP Server(http) 即插即用注册。
        # 依赖用户主机先起 WeKnora 核心 + http 模式 MCP Server；未配置
        # WEKNORA_MCP_URL 或不可达时静默跳过，绝不谎报 live。
        try:
            self.register_weknora_mcp()
        except Exception as e:  # noqa: BLE001 - 远端/网络故障不拖垮枢纽
            _LOG.warning("WeKnora MCP 注册失败(将跳过): %s", e)
        # 本机 IDA Pro 逆向工程 MCP（mrexodia/ida-pro-mcp，真实开源）：仅当
        # IDA_PRO_MCP_URL 配置且为 localhost 时注册 re.ida 芯粒；非本机 URL 或
        # IDA 未运行则静默跳过，绝不谎报 live（红线：仅连你自己机器上的 IDA）。
        try:
            self.register_ida_pro_mcp()
        except Exception as e:  # noqa: BLE001
            _LOG.warning("ida-pro-mcp 注册失败(将跳过): %s", e)
        # codebase-memory-mcp 是 stdio-only 的 MCP server（纯 C / 零依赖 / MIT），
        # 现有 register_mcp_server 只接 HTTP(SSE)，接不上它。这里单独接 stdio
        # 传输，并把真实工具「弄进」AOS：二进制缺失时优雅跳过，绝不谎报 live。
        self._register_env_codebase_mcp()
        # Desktop-Touch-MCP：Windows 原生 UIA 桌面视觉执行芯粒（stdio MCP）。
        # 默认关闭（需在用户 Windows 主机装 Node + 授权辅助功能，沙箱/CI 不拉起
        # npx）；设 DESKTOP_TOUCH_MCP_ENABLED=1 时启动即自动 npx 拉起并注册。
        if os.environ.get("DESKTOP_TOUCH_MCP_ENABLED") == "1":
            try:
                self.register_desktop_touch_mcp()
            except Exception as e:  # noqa: BLE001 - 远端/网络故障不拖垮枢纽
                _LOG.warning("Desktop-Touch-MCP 注册失败(将跳过): %s", e)
        # Omni-Video Studio MCP（omni-video-mcp，Python stdio MCP 视频剪辑芯粒）。
        # 默认关闭；设 OMNI_VIDEO_MCP_ENABLED=1 启动时自动拉起。需用户主机装 ffmpeg
        # + ELEVENLABS_API_KEY + Playwright(chromium)，二进制/依赖缺失时优雅跳过。
        if os.environ.get("OMNI_VIDEO_MCP_ENABLED") == "1":
            try:
                self.register_omni_video_mcp()
            except Exception as e:  # noqa: BLE001
                _LOG.warning("Omni-Video MCP 注册失败(将跳过): %s", e)
        # video-use（npm stdio MCP 轻量视频关键帧提取芯粒）。默认关闭；设
        # VIDEO_USE_MCP_ENABLED=1 启动时自动 npx 拉起。需 ffmpeg + yt-dlp(URL源)。
        if os.environ.get("VIDEO_USE_MCP_ENABLED") == "1":
            try:
                self.register_video_use_mcp()
            except Exception as e:  # noqa: BLE001
                _LOG.warning("video-use MCP 注册失败(将跳过): %s", e)
        # 默认通电编排芯粒：让 system.workflow 能力在构建后即 live，
        # run_task 的底层编排才不会因「no live provider」空转。
        # （之前只有显式 add_orchestrator() 才挂，health_report 里
        #  system.workflow 永远显示未通电，run_task 默认跑不出编排。）
        try:
            self.add_orchestrator()
        except Exception as e:  # noqa: BLE001 - 编排芯粒注册失败不拖垮枢纽
            _LOG.warning("默认注册编排芯粒失败: %s", e)
        # code_team 多智能体代码团队：接成可路由引擎（code.generate 能力），
        # 让它从「独立 API 端点孤岛」进入统一能力路由（健康/预测器/透明化）。
        try:
            self.register_code_team()
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("默认注册 code_team 引擎失败: %s", e)
        # ComfyUI 本地视觉生产引擎：接成可路由芯粒（media.image / media.video），
        # 让一句话 prompt 经 hub 自动落到本地 ComfyUI 出图（本地优先于云端 agnes）。
        try:
            self.register_comfyui()
            self.register_content_director()
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("默认注册 comfyui 引擎失败: %s", e)
        # 后台预热重型依赖（autogen 80s / litellm 22s import），避免 health/
        # 初始化被卡死。预热期间 guarded_import 命中 _WARMING 直接返回 None，
        # health 如实标 dead，预热线程完成后再标 live，全程不阻塞调用方。
        try:
            from ..resilience import prewarm
            prewarm(["autogen", "litellm", "mem0ai", "mem0"])
        except Exception:  # noqa: BLE001
            pass
        # MAST 式失败监控：接全局单例（best-effort，失败不拖垮枢纽）。
        # 让 route() 的真实失败流量被埋点采集，监控器从死模块变可观测。
        try:
            from kernel.plugins.failure_monitor import get_failure_monitor
            self._failure_monitor = get_failure_monitor()
        except Exception as e:  # noqa: BLE001
            _LOG.warning("接入失败监控器失败（非致命）: %s", e)
            self._failure_monitor = None

    # ---- 模拟路由层（仅探测用，生产默认关闭） --------------------
    def set_route_sim_us(self, micros: float) -> None:
        """设置模拟路由延迟（微秒）。0 表示关闭。仅用于 IPC 开销探测。"""
        self.route_sim_us = float(micros)

    # ---- 公共 API -------------------------------------------------
    def resolve_engine(self, capability: str) -> Optional[str]:
        """能力→引擎 单一可信源：返回能服务该能力的 live 引擎 id；无则 None。

        关键不变量：返回的引擎一定 health()==True（绝不谎报 live）。
        """
        for eid, adapter in self._registry._adapters.items():
            caps = [c.value if hasattr(c, "value") else str(c)
                    for c in adapter.advertise_capabilities()]
            if capability in caps and adapter.health():
                return eid
        return None

    def register_adapter(self, adapter) -> None:
        """向 FabricHub 注册一个适配器。

        用于动态注册新能力（如 AutoSkill 安装的技能、运行时发现的新引擎）。
        """
        self._registry.register(adapter)
        _LOG.info("FabricHub 动态注册适配器: %s", getattr(adapter, "engine_id", "unknown"))

    def add_missing_capability_hook(self, hook: Callable) -> None:
        """注册能力缺失钩子——当某个能力没有 live provider 时触发。

        钩子签名：hook(capability: str, payload: dict) -> bool
        返回 True 表示钩子成功补充了能力（注册了新 adapter），可以重试路由。

        典型用例：AutoSkill 引擎——缺什么技能自动去 SkillHub 找并安装注册。
        """
        self._missing_capability_hooks.append(hook)

    def _run_missing_capability_hooks(self, capability: str, payload: Dict[str, Any]) -> bool:
        """运行所有能力缺失钩子，任意一个返回 True 就认为成功补充了能力。"""
        if not self._missing_capability_hooks:
            return False
        for hook in self._missing_capability_hooks:
            try:
                if hook(capability, payload):
                    _LOG.info("能力缺失钩子成功补充: %s", capability)
                    return True
            except Exception as e:  # noqa: BLE001 - 钩子失败不影响主流程
                _LOG.warning("能力缺失钩子异常: %s", e)
        return False

    def route(self, capability: str, payload: Dict[str, Any],
              trace_id: Optional[str] = None) -> Any:
        """经能力路由把请求委派给 live 引擎，并在供给方之间做**运行时故障转移**：

        依偏好（云端优先→本地兜底）逐个尝试，某芯粒 `ok=False` 或抛异常
        则自动跳到下一个 live 供给方——这正是「云端用不了就本地 / 万物为我所用」
        的真实执行路径，调用方不感知背后是云还是端。

        异常隔离：任一芯粒 invoke 抛异常都会被单独捕获并记故障时间戳，返回干净的
        InvokeResult(ok=False)，绝不穿透到调用方/内核/其他芯粒
        （对应 Chiplet 故障隔离；Day11-14 闸门3 的「不传染」属性）。

        若 route_sim_us>0，则在委派前忙等该微秒数，模拟内核↔芯粒这一跳的
        IPC 延迟（Named Pipe ~20μs），供 ipc_probe 测量开销占比。
        """
        if self.route_sim_us:
            _busy_wait(self.route_sim_us / 1_000_000.0)
        req = InvokeRequest(capability=capability, payload=payload, trace_id=trace_id,
                            tier=payload.get("tier"))
        # 白盒进化：真实流量前，若已积累够新样本则自动重训（learned 策略下）。
        self._registry.maybe_retrain()
        # MAST 失败监控：记录任务开始（best-effort，异常不影响路由）。
        fm = self._failure_monitor
        if fm is not None:
            try:
                fm.record_task_start()
            except Exception:  # noqa: BLE001
                pass
        cap_str = self._registry.capability_to_str(capability)
        eff_tier = req.tier or self._registry.tier
        providers = self._registry.providers_for(req.capability, req.tier)
        if not providers:
            # 能力缺失钩子：AutoSkill 等模块可以在这里自动发现并安装技能
            if self._run_missing_capability_hooks(capability, payload):
                # 钩子成功补充了能力，重新获取 providers
                providers = self._registry.providers_for(req.capability, req.tier)
        # 白盒蒸馏沉底：把被蒸馏器判为不可靠的引擎排到末尾（有可靠备选才跳过）。
        if self._distiller is not None:
            providers = self._reorder_by_distiller(capability, providers)
        if not providers:
            return InvokeResult(ok=False, error=f"no live provider for {capability}")
        last_res: InvokeResult | None = None
        last_eid: str | None = None
        attempts: list[str] = []
        for adapter in providers:
            eid = adapter.engine_id
            t0 = time.perf_counter()
            try:
                res = adapter.invoke(req)
            except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
                dt = (time.perf_counter() - t0) * 1000.0
                self._failures[eid] = time.perf_counter()
                self._errors[eid] = f"invoke failed: {e!r}"
                _LOG.warning("fabric 芯粒 %s invoke 异常已隔离: %s", eid, e)
                self._registry.record_outcome(cap_str, eid, eff_tier, False, dt, error=repr(e))
                self._feed_distiller(cap_str, eid, False, repr(e))
                attempts.append(f"{eid} raised: {e!r}")
                continue
            dt = (time.perf_counter() - t0) * 1000.0
            if res.ok:
                self._registry.record_outcome(cap_str, eid, eff_tier, True, dt)
                self._feed_distiller(cap_str, eid, True, None)
                if fm is not None:
                    try:
                        fm.record_success()
                    except Exception:  # noqa: BLE001
                        pass
                # 媒体能力统一契约投影：保证 data 同时含 url/output/output_path
                # 三键（与 core.fabric.adapter.normalize_media_data 一致），使所有
                # 消费方只需读 `url` 一个键即可，根除历史四态分裂导致的静默失败。
                res_data = normalize_media_data(res.data) if cap_str.startswith("media.") else res.data
                # 回填真实执行引擎 id（理念6：诚实呈现「哪个引擎跑的」）。
                # 优先采纳适配器回报的 engine_id——当某适配器内部回落到别的
                # 引擎（如 code-exec 离线回落 code-team）时，被回填的是真正
                # 干活的引擎，而非 route 选中的派发壳；适配器未标注时才退回
                # route 选中的 eid。下游 trace / A2UI / 预测器观测据此拿真相。
                return InvokeResult(
                    ok=True, data=res_data, error=res.error,
                    engine_id=res.engine_id or eid)
            self._failures[eid] = time.perf_counter()
            self._errors[eid] = res.error or "ok=False"
            self._registry.record_outcome(
                cap_str, eid, eff_tier, False, dt,
                error=res.error if not res.ok else None,
            )
            self._feed_distiller(cap_str, eid, False, res.error)
            attempts.append(f"{eid}: {res.error}")
            last_res = res
            last_eid = eid
        # 全部失败：埋点进 MAST 失败监控（best-effort，绝不影响返回结果）。
        if fm is not None and last_res is not None:
            try:
                self._record_failure(capability, last_res.error, last_eid, attempts)
            except Exception:  # noqa: BLE001
                pass
        # 全部失败：返回最后一个芯粒的真实结果（保留其 data，如编排 trace/
        # ok_steps），错误附注「已协商 N 个芯粒」以体现端云合作耗尽，而非合成
        # data=None 把下游有用的失败上下文吞掉。
        if last_res is not None:
            return InvokeResult(
                ok=False,
                data=last_res.data,
                error=f"all providers failed [{capability}] "
                      f"after {len(attempts)} attempt(s): " + " | ".join(attempts),
                engine_id=last_eid,
            )
        return InvokeResult(
            ok=False,
            data={
                "capability": capability,
                "attempts": attempts,
                "engine_errors": {
                    eid: self._errors.get(eid, "unknown")
                    for eid in [a.split(":")[0].strip() for a in attempts]
                },
            },
            error=f"all providers raised [{capability}]: " + " | ".join(attempts),
        )

    # ---- 白盒蒸馏路由（理念8/2.5 闭环消费端） --------------------
    def _reorder_by_distiller(self, capability: str, providers: list) -> list:
        """把被蒸馏器判不可靠的引擎排到末尾；有可靠备选且 AOS_DISTILLER_DROP=1
        时才硬跳过（诚实：无备选仍保留兜底，绝不静默丢弃能力）。"""
        if not providers:
            return providers
        try:
            sunk = {s["engine"] for s in self._distiller.distill()
                    if s.get("capability") == capability}
        except Exception:  # noqa: BLE001
            return providers
        if not sunk:
            return providers
        kept, moved = [], []
        for a in providers:
            (moved if a.engine_id in sunk else kept).append(a)
        if self._distill_drop and kept:
            return kept  # 有可靠备选才跳过沉底引擎
        return kept + moved

    def _feed_distiller(self, capability: str, engine: str, ok: bool,
                        error: Optional[str]) -> None:
        """把单次路由 outcome 喂给蒸馏器（best-effort，异常不影响路由）。"""
        if self._distiller is None:
            return
        try:
            self._distiller.record_outcome(capability, engine, ok, error or "")
        except Exception:  # noqa: BLE001
            pass

    # ---- MAST 失败监控埋点（best-effort，绝不影响主路由） ----
    def _record_failure(self, capability: str, error: Optional[str],
                        engine_id: Optional[str], attempts: list) -> None:
        """把一次路由失败埋点进 MAST 失败监控器（理念6 可观测）。"""
        fm = self._failure_monitor
        if fm is None:
            return
        try:
            mode = self._classify_failure(error)
            fm.record(
                mode,
                agent_id=engine_id or "router",
                task_id=capability,
                message=error or "all candidates failed: " + " | ".join(attempts[:3]),
            )
        except Exception:  # noqa: BLE001 - 监控埋点失败不影响主流程
            pass

    @staticmethod
    def _classify_failure(error: Optional[str]):
        """把路由失败错误粗略映射到 MAST 失败模式（失败分类观测量化）。"""
        from kernel.plugins.failure_monitor import FailureMode  # 函数内 import 避免循环
        e = (error or "").lower()
        if "timeout" in e or "timed out" in e:
            return FailureMode.TIMEOUT
        if "permission" in e or "denied" in e or " 403" in e or "403 " in e:
            return FailureMode.PERMISSION_DENIED
        if "unavailable" in e or "not reachable" in e or "connection" in e or "refused" in e:
            return FailureMode.MODEL_UNAVAILABLE
        if "protocol" in e or "mcp" in e or "a2a" in e:
            return FailureMode.PROTOCOL_ERROR
        if "silent" in e or "empty" in e or "none" in e:
            return FailureMode.SILENT_FAILURE
        return FailureMode.VERIFY_FAILURE

    def invoke_engine(self, engine_id: str, capability: str,
                      payload: Dict[str, Any]) -> InvokeResult:
        """直接打指定引擎（绕过能力路由的「首个 live」选择）。

        - 隔离引擎(B 路线子进程)：走 IsolatedEngineHost.invoke；
        - 进程内引擎：从 registry 取适配器直接 invoke；
        - 未知引擎 / 异常：返回干净的 InvokeResult(ok=False)，绝不抛。
        用于 MCP / 外部调用方精确指定目标芯粒（如按 engine_id 委派）。
        """
        host = self._isolated.get(engine_id)
        if host is not None:
            # IsolatedEngineHost.invoke 返回 dict（子进程 worker 结果）。
            resp = host.invoke(capability, payload)
            if isinstance(resp, dict):
                return InvokeResult(ok=resp.get("ok", False),
                                    data=resp.get("data"), error=resp.get("error"))
            return resp
        adapter = self._registry.get(engine_id)
        if adapter is None:
            return InvokeResult(ok=False, error=f"unknown engine {engine_id}")
        try:
            return adapter.invoke(InvokeRequest(capability=capability, payload=payload))
        except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
            self._errors[engine_id] = f"invoke failed: {e!r}"
            _LOG.warning("fabric 芯粒 %s invoke 异常已隔离: %s", engine_id, e)
            return InvokeResult(ok=False, error=f"{engine_id} invoke failed: {e!r}")

    # ---- 外部 MCP Server 即插即用 ---------------------------------
    def register_mcp_server(
        self,
        server_url: str,
        engine_id: Optional[str] = None,
        capability_map: Optional[dict] = None,
        auth_token: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[str]:
        """把一个外部 MCP Server 注册成 AOS 芯粒。

        这是「万物为我所用」的协议级落点：任何支持 MCP 的服务（已验证
        AnySearch / ExploreYC / Sim / Auriko / Timbal 均支持）都能成为 AOS
        供给方，其 tools 经 capability_map 映射成 AOS 能力，由 registry 统一
        路由与故障转移。返回注册的 engine_id；失败返回 None 并记错误。
        """
        try:
            from core.fabric.adapters.mcp_client_adapter import MCPClientAdapter
            eid = engine_id or f"mcp-{server_url.rstrip('/').split('/')[-1]}"
            adapter = MCPClientAdapter(
                server_url=server_url,
                engine_id=eid,
                capability_map=capability_map,
                auth_token=auth_token,
                timeout=timeout,
            )
            self._registry.register(adapter)
            return eid
        except Exception as e:  # noqa: BLE001 - 远端/网络故障不拖垮枢纽
            self._errors[f"mcp:{server_url}"] = repr(e)
            _LOG.warning("MCP Server 注册失败 %s: %s", server_url, e)
            return None

    def _register_env_mcp_servers(self) -> None:
        raw = os.environ.get("AOS_MCP_SERVERS")
        if not raw:
            return
        try:
            servers = json.loads(raw)
        except json.JSONDecodeError as e:
            _LOG.warning("AOS_MCP_SERVERS 非法 JSON: %s", e)
            return
        if not isinstance(servers, list):
            return
        for spec in servers:
            if not isinstance(spec, dict) or not spec.get("url"):
                continue
            self.register_mcp_server(
                server_url=spec["url"],
                engine_id=spec.get("engine_id"),
                capability_map=spec.get("capability_map"),
                auth_token=spec.get("auth_token"),
                timeout=spec.get("timeout", 10.0),
            )

    # ---- WeKnora（腾讯开源 RAG/知识引擎）MCP 即插即用 ------------
    def register_weknora_mcp(
        self,
        url: Optional[str] = None,
        engine_id: str = "weknora",
        auth_token: Optional[str] = None,
        capability_map: Optional[dict] = None,
        timeout: float = 15.0,
    ) -> Optional[str]:
        """把腾讯开源的 WeKnora 知识引擎（经其 MCP Server）注册成 AOS 芯粒。

        WeKnora 是真实开源项目（github.com/Tencent/WeKnora, MIT 许可证）：
        RAG 问答 + ReAct Agent + 自动 Wiki，覆盖 PDF/Word/图片/Excel 等十余种
        格式，兼容 20+ 大模型。其 MCP Server 支持 stdio/sse/http 三种传输；
        这里走 http(Streamable HTTP) 模式，直接复用现有 MCPClientAdapter，
        零新组件、不弄虚。

        前置（用户主机，沙箱无法跑 Docker）：
          1) 起 WeKnora 核心：在 WeKnora 仓库 `docker compose up -d`（REST :8080）
          2) 起 MCP Server(http)：`python weknora_mcp_server.py --transport http
             --host 0.0.0.0 --port 8081`，并给该进程设 WEKNORA_API_KEY +
             WEKNORA_BASE_URL（默认 http://localhost:8080/api/v1）以及
             MCP_SERVER_AUTH_TOKEN（MCP 网络传输鉴权，须与下方 AOS 侧一致）
        然后 AOS 侧设 WEKNORA_MCP_URL=http://localhost:8081/mcp 即可自动注册。

        capability_map 默认：hybrid_search→data.query，chat→memory.knowledge，
        agent_chat→cognition.reasoning，wiki_search→memory.knowledge；其余工具
        未映射时由适配器按 action.tool_use 暴露。返回 engine_id；失败返回 None
        并记错误（绝不谎报 live）。
        """
        url = url or os.environ.get("WEKNORA_MCP_URL")
        if not url:
            return None
        auth_token = auth_token or os.environ.get("WEKNORA_MCP_AUTH_TOKEN")
        engine_id = os.environ.get("WEKNORA_MCP_ENGINE_ID") or engine_id
        if capability_map is None:
            capability_map = {
                "hybrid_search": "data.query",
                "chat": "memory.knowledge",
                "agent_chat": "cognition.reasoning",
                "wiki_search": "memory.knowledge",
            }
        return self.register_mcp_server(
            server_url=url,
            engine_id=engine_id,
            capability_map=capability_map,
            auth_token=auth_token,
            timeout=timeout,
        )

    # ---- ida-pro-mcp（本机 IDA Pro 逆向工程 MCP）即插即用 ------------
    def register_ida_pro_mcp(
        self,
        url: Optional[str] = None,
        engine_id: str = "ida-pro-mcp",
        auth_token: Optional[str] = None,
        timeout: float = 15.0,
    ) -> Optional[str]:
        """把本机 mrexodia/ida-pro-mcp（真实开源逆向工程 MCP，MIT）注册成 AOS re.ida 芯粒。

        前置（用户主机，沙箱无法跑 IDA）：
          1) pip install --upgrade git+https://github.com/mrexodia/ida-pro-mcp
          2) ida-pro-mcp --install   # 安装 IDA 插件
          3) 启动 IDA 并加载目标二进制（.idb/.i64）
          4) 设 IDA_PRO_MCP_URL=http://localhost:<port>/mcp
        AOS 侧在 IDA_PRO_MCP_URL 存在且为 localhost 时自动注册；否则返回 None（opt-in）。

        红线：非 localhost URL 一律拒绝注册（绝不连你无权分析的第三方 IDA 实例）。
        返回 engine_id；IDA 未运行/不可达时返回 None 并记警告（绝不谎报 live）。
        """
        url = url or os.environ.get("IDA_PRO_MCP_URL")
        if not url:
            return None
        host = url.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower()
        if host not in ("localhost", "127.0.0.1", "::1", "0.0.0.0") and not host.endswith(".localhost"):
            _LOG.warning(
                "IDA_PRO_MCP_URL 非 localhost，拒绝注册（红线：仅连你自己机器上的 IDA）：%s",
                url,
            )
            return None
        try:
            adapter = IdaProMcpAdapter(
                server_url=url, engine_id=engine_id,
                auth_token=auth_token, timeout=timeout,
            )
        except Exception as e:  # noqa: BLE001 - IDA 未运行等，优雅跳过
            _LOG.warning("ida-pro-mcp 注册失败（IDA 未运行？）：%s", e)
            return None
        self.register_adapter(adapter)
        return engine_id

    # ---- Desktop-Touch-MCP（Windows 原生 UIA 桌面视觉执行）即插即用 --
    def register_desktop_touch_mcp(
        self,
        command: Optional[list] = None,
        engine_id: str = "desktop-touch",
        capability_map: Optional[dict] = None,
        timeout: float = 30.0,
    ) -> Optional[str]:
        """把 Desktop-Touch-MCP（Harusame64，Windows 原生 UI Automation MCP 服务）
        注册成 AOS 桌面视觉执行芯粒（action.aci 能力）。

        真实开源项目（github.com/Harusame64/desktop-touch-mcp，MIT 许可证）：
        Rust 原生 UIA 内核（getFocusedElement 2ms）、29+ 工具、强中文(CJK/IME)
        支持、npx 零配置。通过 AOS 既有的 MCPStdioAdapter 直连其 stdio 传输，
        零新组件、不弄虚——与 WeKnora / codebase-memory-mcp 同一「万物为我所用」
        协议级落点。

        前置（用户 Windows 主机，沙箱无桌面跑不了）：
          1) 装 Node.js v20+（官方测过 v22+）；
          2) 起 AOS 时自动 `npx -y @harusame64/desktop-touch-mcp`（或设
             DESKTOP_TOUCH_MCP_CMD 自定义命令，如本地 clone 后的 dist/index.js）；
          3) 首次运行 npx 会从 GitHub Releases 拉运行时 zip（国内/共享网络可能
             触发 60 次/小时匿名限速，设 GITHUB_TOKEN 提到 5000/小时）；需装
             Visual C++ Redistributable（nut-js 原生绑定依赖）；建议把解压目录
             %USERPROFILE%/.desktop-touch-mcp 加 Defender 白名单，避免被杀软拦截。
             Windows 下 UIA 一般无需 macOS 式辅助功能开关；急停=鼠标移到屏幕
             左上角(0,0)10px 内即终止服务。
        capability_map 默认把桌面发现/操作/截图类 tool 映射到 action.aci；
        返回 engine_id；失败返回 None 并记错误（MCPStdioAdapter 启动失败即
        health=False，绝不谎报 live）。
        """
        engine_id = os.environ.get("DESKTOP_TOUCH_MCP_ENGINE_ID") or engine_id
        raw_cmd = command or os.environ.get(
            "DESKTOP_TOUCH_MCP_CMD", "npx -y @harusame64/desktop-touch-mcp"
        )
        if isinstance(raw_cmd, str):
            raw_cmd = raw_cmd.split()
        if capability_map is None:
            capability_map = {
                "desktop_discover": "action.aci",
                "desktop_act": "action.aci",
                "desktop_state": "action.aci",
                "screenshot": "action.aci",
                "mouse_click": "action.aci",
                "mouse_move": "action.aci",
                "keyboard_type": "action.aci",
                "keyboard_press": "action.aci",
                "clipboard_read": "action.aci",
                "clipboard_write": "action.aci",
                "window_list": "action.aci",
                "window_focus": "action.aci",
            }
        try:
            from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter
            adapter = MCPStdioAdapter(
                command=list(raw_cmd),
                engine_id=engine_id,
                capability_map=capability_map,
                timeout=timeout,
            )
            self._registry.register(adapter)
            return engine_id
        except Exception as e:  # noqa: BLE001 - 二进制缺失/握手失败不拖垮枢纽
            self._errors[f"desktop-touch:{engine_id}"] = repr(e)
            _LOG.warning("Desktop-Touch-MCP 注册失败 %s: %s", engine_id, e)
            return None

    # ---- omni-video-mcp（stdio MCP）专业视频剪辑芯粒 ----------------
    def register_omni_video_mcp(
        self,
        command: Optional[list] = None,
        engine_id: str = "omni-video",
        capability_map: Optional[dict] = None,
        timeout: float = 60.0,
        cwd: Optional[str] = None,
    ) -> Optional[str]:
        """把 omni-video-mcp（真实 Python stdio MCP 视频剪辑服务）注册成 AOS
        media.video 芯粒。

        真实开源项目（github.com/buildwithtaza/omni-video-mcp，企业级视频剪辑 MCP，
        「Omni-Video Studio MCP」即其别名）。四阶段流水线：omni_video_ingest(摄取
        转录+视觉场景图) / omni_video_preview(胶片条预览) / omni_video_generate_vfx
        (Hyperframes 动效) / omni_video_render(FFmpeg 最终母带，支持 EDL 剪辑/LUT
        调色/音频修复/字幕烧录)。与 Desktop-Touch-MCP 同一「协议级接入」落点——AOS
        不重写它的脑子，只是用 MCPStdioAdapter 直连 stdio 传输。详情见
        docs/VIDEO_MCP_INTEGRATION.md。

        前置（用户 Windows 主机）：
          1) 克隆仓库并装依赖：uv venv && uv pip install -e . && playwright install chromium；
          2) 系统装 ffmpeg（PATH 可达）；
          3) 设 ELEVENLABS_API_KEY（高保真逐词转录所需）；
          4) 设 OMNI_VIDEO_MCP_CMD 指向实际启动命令，如
             "uv run /d/AI_Model/omni-video-mcp/server.py"（或 "python server.py"）；
          5) 设 OMNI_VIDEO_MCP_ENABLED=1 后启动 AOS 即自动拉起注册。
        capability_map 默认把 omni_video_* 工具映射到 media.video；返回 engine_id；
        失败返回 None 并记错误（MCPStdioAdapter 启动失败即 health=False，绝不谎报 live）。
        """
        engine_id = os.environ.get("OMNI_VIDEO_MCP_ENGINE_ID") or engine_id
        repo = os.environ.get("OMNI_VIDEO_MCP_REPO")
        raw_cmd = command or os.environ.get("OMNI_VIDEO_MCP_CMD")
        resolved_cwd = cwd
        if raw_cmd is None:
            if repo:
                resolved_cwd = repo
                srv = os.path.join(repo, "server.py")
                # 优先用仓库内 .venv 的 python 直接拉起，避免 uv sync 重触发
                # 项目自身的 editable build（受限环境会失败且无必要）。
                venv_py = None
                for cand in (
                    os.path.join(repo, ".venv", "Scripts", "python.exe"),
                    os.path.join(repo, ".venv", "bin", "python"),
                ):
                    if os.path.exists(cand):
                        venv_py = cand
                        break
                if venv_py:
                    raw_cmd = f"{venv_py} {srv}"
                else:
                    uv_bin = (
                        os.environ.get("OMNI_VIDEO_MCP_UV_BIN")
                        or shutil.which("uv")
                        or r"C:\Users\Administrator\AppData\Local\hermes\bin\uv"
                    )
                    raw_cmd = f"{uv_bin} run {srv}"
            else:
                raw_cmd = "uv run server.py"
        if isinstance(raw_cmd, str):
            raw_cmd = raw_cmd.split()
        if capability_map is None:
            capability_map = {
                "omni_video_ingest": "media.video",
                "omni_video_preview": "media.video",
                "omni_video_generate_vfx": "media.video",
                "omni_video_render": "media.video",
            }
        try:
            from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter
            adapter = MCPStdioAdapter(
                command=list(raw_cmd),
                engine_id=engine_id,
                capability_map=capability_map,
                timeout=timeout,
                cwd=resolved_cwd,
            )
            self._registry.register(adapter)
            return engine_id
        except Exception as e:  # noqa: BLE001 - 二进制缺失/握手失败不拖垮枢纽
            self._errors[f"omni-video:{engine_id}"] = repr(e)
            _LOG.warning("Omni-Video MCP 注册失败 %s: %s", engine_id, e)
            return None

    # ---- video-use（stdio MCP）轻量视频关键帧提取芯粒 --------------
    def register_video_use_mcp(
        self,
        command: Optional[list] = None,
        engine_id: str = "video-use",
        capability_map: Optional[dict] = None,
        timeout: float = 60.0,
    ) -> Optional[str]:
        """把 video-use（真实 npm stdio MCP 视频关键帧提取服务）注册成 AOS
        media.video 芯粒。

        真实开源包（npm: video-use，v0.1.1）。MCP 服务+CLI，从本地文件或视频 URL
        下载并提取关键帧（场景变化检测+兜底 FPS 采样+时间去重），让 AI 用图像+
        时间戳「看懂」视频。与 Desktop-Touch-MCP 同一「协议级接入」落点。详情见
        docs/VIDEO_MCP_INTEGRATION.md。

        前置（用户 Windows 主机）：
          1) 系统装 ffmpeg（PATH 可达）、yt-dlp（仅 URL 源需要）；
          2) Node.js v20+；
          3) 设 VIDEO_USE_MCP_CMD 自定义命令（默认 "npx -y video-use"）；
          4) 设 VIDEO_USE_MCP_ENABLED=1 后启动 AOS 即自动 npx 拉起注册。
        capability_map 默认把 video_frames_extract/video_probe/video_cleanup 映射到
        media.video；返回 engine_id；失败返回 None 并记错误（绝不谎报 live）。
        """
        engine_id = os.environ.get("VIDEO_USE_MCP_ENGINE_ID") or engine_id
        raw_cmd = command or os.environ.get("VIDEO_USE_MCP_CMD")
        if raw_cmd is None:
            # Windows 优先用全局 npm bin 的 .cmd（subprocess 直接调无扩展名 shim 会 WinError 2 找不到）
            npm_bin = os.environ.get("APPDATA", "")
            if npm_bin:
                cand = os.path.join(npm_bin, "npm", "video-use.cmd")
                if os.path.exists(cand):
                    raw_cmd = cand
            if raw_cmd is None:
                raw_cmd = "npx -y video-use"
        if isinstance(raw_cmd, str):
            raw_cmd = raw_cmd.split()
        if capability_map is None:
            capability_map = {
                "video_frames_extract": "media.video",
                "video_probe": "media.video",
                "video_cleanup": "media.video",
            }
        try:
            from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter
            adapter = MCPStdioAdapter(
                command=list(raw_cmd),
                engine_id=engine_id,
                capability_map=capability_map,
                timeout=timeout,
            )
            self._registry.register(adapter)
            return engine_id
        except Exception as e:  # noqa: BLE001 - 二进制缺失/握手失败不拖垮枢纽
            self._errors[f"video-use:{engine_id}"] = repr(e)
            _LOG.warning("video-use MCP 注册失败 %s: %s", engine_id, e)
            return None

    # ---- codebase-memory-mcp（stdio MCP）即插即用 -----------------
    def register_codebase_mcp(
        self,
        bin_path: str,
        repo_path: Optional[str] = None,
        engine_id: str = "codebase-memory-mcp",
        timeout: float = 60.0,
    ) -> Optional[str]:
        """把 codebase-memory-mcp（真实 stdio MCP server）注册成 AOS 芯粒。

        这是「把真实开源工具弄进 AOS」的落点：AOS 不重写它的脑子，只是用
        stdio MCP 客户端把它接成 `code.understanding` 能力供给方。返回 engine_id；
        失败返回 None 并记错误（绝不谎报 live）。
        """
        try:
            from core.fabric.adapters.codebase_memory_mcp_adapter import (
                build_codebase_mcp_adapter,
            )
            adapter = build_codebase_mcp_adapter(
                bin_path,
                repo_path or self._project_root(),
                engine_id=engine_id,
                timeout=timeout,
            )
            self._registry.register(adapter)
            return engine_id
        except Exception as e:  # noqa: BLE001 - 二进制缺失/握手失败不拖垮枢纽
            self._errors[f"codebase-mcp:{bin_path}"] = repr(e)
            _LOG.warning("codebase-memory-mcp 注册失败 %s: %s", bin_path, e)
            return None

    # ---- code_team 多智能体代码团队（本地芯粒）-------------------
    def register_comfyui(self) -> None:
        """把本地 ComfyUI 视觉生产引擎接成可路由芯粒（media.image / media.video）。

        此前 ComfyUI 只在 legacy brain 栈里是个 Skill，FabricHub 新栈的
        media.image/media.video 路由给本地 ComfyUI（HIGH 优先）与国产 media-gen（MEDIUM 兜底），
        本地那台 ComfyUI 已被新栈看见并优先。接进来后：
        - ``hub.route("media.image", {prompt})`` 一句话可达、自动出图；
        - health_report 列出 comfyui 为 live（探 /system_info，没起如实 False）；
        - 真实流量喂路由预测器；享引擎透明化（engine_id="comfyui"）；
        - 本地 high 档优先于云端 agnes，route 级联「云端用不了就本地」。
        适配器构造轻量（仅 import + 探活）；构造失败静默跳过，绝不谎报 live。
        """
        try:
            from kernel.plugins.comfyui_adapter import ComfyUIAdapter
            self._registry.register(ComfyUIAdapter())
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("comfyui 引擎注册失败(将跳过): %s", e)

    def register_code_team(self) -> None:
        """把 code_team 多智能体代码团队接成可路由引擎（code.generate 能力）。

        此前 code_team 只是独立 API 端点 + 模块（孤岛）。接进来后：
        - ``hub.route("code.generate", {requirement, lang})`` 可达；
        - health_report 列出 code-team 为 live；
        - 真实流量喂路由预测器；享引擎透明化（engine_id="code-team"）。
        适配器构造轻量（仅本地 compliance，无重型依赖）；构造失败静默跳过，
        绝不谎报 live。
        """
        try:
            from kernel.plugins.code_team_adapter import CodeTeamAdapter
            self._registry.register(CodeTeamAdapter())
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("code_team 引擎注册失败(将跳过): %s", e)

    def register_content_director(self) -> None:
        """把内容生产导演接成可路由芯粒（content.produce）。

        此前内容生产是概念性缺口——各能力（web.search / media.image / code.generate）
        都已通电，但没有「一句话目标 → 自主跑完整条链路」的编排层。接进来后：
        - ``hub.route("content.produce", {goal})`` 一句话可达，导演自主检索/分析/
          写剧本/导演(动态编排节点图)/调工具/出审核包；
        - 复用 hub 单一可信路由（与 OrchestrationChiplet 同构），本地优先/零成本；
        - 审核为 human-in-the-loop 停点，approve 才发布（不自动越过）。
        适配器构造轻量（仅 import）；构造失败静默跳过，绝不谎报 live。
        """
        try:
            from kernel.plugins.content_director import ContentDirector
            self._registry.register(ContentDirector(route_fn=self.route))
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("content_director 引擎注册失败(将跳过): %s", e)

        try:
            from core.fabric.adapters.content_marketer_adapter import ContentMarketerAdapter
            self._registry.register(ContentMarketerAdapter(route_fn=self.route))
        except Exception as e:  # noqa: BLE001 - 芯粒注册失败不拖垮枢纽
            _LOG.warning("content_marketer 引擎注册失败(将跳过): %s", e)

        try:
            from core.fabric.adapters.cast_adapter import CastAdapter
            self._registry.register(CastAdapter(route_fn=self.route))
        except Exception as e:  # noqa: BLE001
            _LOG.warning("cast 引擎注册失败(将跳过): %s", e)

        try:
            from core.fabric.adapters.echo_adapter import EchoAdapter
            echo = EchoAdapter(route_fn=self.route)
            # 可选：注入 PulseCollector，让内容飞轮的反馈数据也进 Pulse，
            # 供 Evolve 做内容优化分析（best-effort，失败不影响主流程）
            try:
                from kernel.pulse.pulse_collector import get_pulse_collector
                echo.set_pulse(get_pulse_collector())
            except Exception:  # noqa: BLE001
                pass
            self._registry.register(echo)
        except Exception as e:  # noqa: BLE001
            _LOG.warning("echo 引擎注册失败(将跳过): %s", e)

        try:
            from core.fabric.adapters.refine_adapter import RefineAdapter
            self._registry.register(RefineAdapter(route_fn=self.route))
        except Exception as e:  # noqa: BLE001
            _LOG.warning("refine 引擎注册失败(将跳过): %s", e)

    def _register_env_codebase_mcp(self) -> None:
        """环境驱动自动注册：让真实工具「装好即通电」，无需改代码。

        - 优先读 AOS_CODEBASE_MCP_BIN（显式二进制路径）；
        - 未设则探测仓库内 install.ps1 的默认安装位
          third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe；
        - 二进制不存在则静默跳过（优雅，不谎报 live）；
        - AOS_CODEBASE_MCP_REPO 可覆盖索引目录（默认仓库根）。
        """
        bin_path = os.environ.get("AOS_CODEBASE_MCP_BIN")
        if not bin_path or not os.path.isfile(bin_path):
            default = (
                Path(self._project_root())
                / "third_party"
                / "codebase-memory-mcp"
                / "bin"
                / "codebase-memory-mcp.exe"
            )
            if default.is_file():
                bin_path = str(default)
        if not bin_path or not os.path.isfile(bin_path):
            return
        repo = os.environ.get("AOS_CODEBASE_MCP_REPO") or self._project_root()
        self.register_codebase_mcp(bin_path, repo_path=repo)

    def _project_root(self) -> str:
        """仓库根（D:/AOS）：本文件位于 src/kernel/plugins/，上溯三级。"""
        return str(Path(__file__).resolve().parents[3])

    def recover(self, eid: str) -> bool:
        """内核重启芯粒：清除故障记录并复探 health()。

        - 进程内(in-process)芯粒对象常驻，重启=复探健康即可恢复服务；
        - 子进程(B 路线)芯粒此处直接 kill+respawn 子进程（≤3s 闸门），
          由 IsolatedEngineHost 完成，其余在途/其他芯粒不受影响。
        返回是否恢复为 live。
        """
        host = self._isolated.get(eid)
        if host is not None:
            ms = host.recover()
            self._recover_ms[eid] = ms
            return host.health()
        adapter = self._registry._adapters.get(eid)
        if adapter is None:
            return False
        self._failures.pop(eid, None)
        self._errors.pop(eid, None)
        return bool(adapter.health())

    def last_failure(self, eid: str) -> Optional[float]:
        """返回该芯粒最近一次 invoke 失败的 perf_counter 时间戳（无则 None）。
        供崩溃恢复耗时度量使用。"""
        return self._failures.get(eid)

    def add_orchestrator(self) -> str:
        """注册「编排芯粒」(system.workflow) 为用户态芯粒。

        关键：编排引擎本身是普通 fabric 适配器，与 litellm/mem0 平级，
        注册进枢纽而非内核——证明工作流堆叠是「封装内容」而非「封装基座」。
        它复用本枢纽的 route() 作为路由层，不另造调度。
        """
        orch = OrchestrationChiplet(route_fn=self.route)
        self._registry.register(orch)
        return orch.engine_id

    def add_isolated_engine(self, engine_id: str, adapter_cls,
                            transport: Optional[str] = None,
                            task_us: float = 0.0, standby: bool = True,
                            passthrough_env: Optional[list[str]] = None) -> str:
        """把一个真实适配器**隔离进独立子进程**，作为 fabric 引擎注册。

        这是 Day22-30 B 路线「收口进生产」的落点：
          - 该引擎的 invoke / health 全部在子进程内执行，崩溃不传染宿主内核；
          - recover(eid) 默认走热备切换（毫秒级，过 3s 恢复闸门，见
            IsolatedEngineHost.standby），无热备时回退冷启动 kill+respawn；
          - 能力路由/自检逻辑复用现有 route()/resolve_engine()/health_report()，
            零改动（注册的是 IsolatedAdapterProxy）。
        默认 transport 取 AOS_ISO_TRANSPORT（沙箱=tcp，生产=pipe/Named Pipe）。
        passthrough_env：隔离层默认剥离全部密钥，适配器确需的 key 经此白名单
        显式回灌子进程（如 agnes 的 AGNES_API_KEY），否则子进程调真实 API 会 401。
        """
        caps = list(adapter_cls().advertise_capabilities())
        spec = f"{adapter_cls.__module__}:{adapter_cls.__qualname__}"
        host = IsolatedEngineHost(engine_id, spec, transport=transport,
                                  task_us=task_us, standby=standby,
                                  passthrough_env=passthrough_env)
        host.start()
        proxy = IsolatedAdapterProxy(engine_id, caps, host)
        self._registry.register(proxy)
        self._isolated[engine_id] = host
        return engine_id

    def health_report(self) -> Dict[str, Any]:
        """诚实通电自检：total / live / 每个引擎状态 / 注册错误。

        这是「知道自己现在到底行不行」的落地——任何引擎 dead 都如实写出，
        而非让调用方静默回退、误以为全链路通。
        """
        report: Dict[str, Any] = {"total": 0, "live": 0, "adapters": {}}
        for eid, adapter in self._registry._adapters.items():
            try:
                live = bool(adapter.health())
                caps = [c.value if hasattr(c, "value") else str(c)
                        for c in adapter.advertise_capabilities()]
                err: Optional[str] = None
            except Exception as e:  # noqa: BLE001
                live, caps, err = False, [], repr(e)
                self._errors[eid] = repr(e)
            report["adapters"][eid] = {
                "live": live,
                "capabilities": caps,
                "error": err,
                "isolated": eid in self._isolated,
            }
            if eid in self._isolated:
                host = self._isolated[eid]
                report["adapters"][eid]["isolation"] = {
                    "subprocess_pid": host.subprocess_pid,
                    "standby_ready": host.standby_ready,
                    "spawn_ms": host.spawn_ms,
                    "rtt_us": host.rtt_us,
                    "last_recover_ms": host.last_recover_ms,
                }
            if hasattr(adapter, "health_detail"):
                try:
                    report["adapters"][eid]["health_detail"] = adapter.health_detail()
                except Exception:  # noqa: BLE001 - 诊断失败绝不拖垮自检
                    pass
            report["total"] += 1
            if live:
                report["live"] += 1
        report["registration_errors"] = dict(self._errors)
        return report

    def advertised(self) -> Dict[str, List[str]]:
        """快照：引擎 id -> 它声明的能力列表。"""
        return self._registry.snapshot()

    def isolation_summary(self) -> Dict[str, Any]:
        """隔离引擎的可观测快照：子进程 PID / 热备就绪 / 三闸门数字 / 上次恢复耗时。

        运维/监控直接吃这份数据，判断隔离引擎「健康到什么程度」，而非仅知道
        它 isolated=True。与 health_report 中每个隔离引擎的 isolation 块同源。
        """
        out: Dict[str, Any] = {}
        for eid, host in self._isolated.items():
            out[eid] = {
                "subprocess_pid": host.subprocess_pid,
                "standby_ready": host.standby_ready,
                "spawn_ms": host.spawn_ms,
                "rtt_us": host.rtt_us,
                "last_recover_ms": host.last_recover_ms,
            }
        return out

    def _known_capabilities(self) -> List[str]:
        """展开当前枢纽通电引擎声明的能力值列表（去重、排序）。

        供 plan_bridge 仅把步骤映射到『实际通电的能力』，避免编排到死引擎。
        """
        caps: set[str] = set()
        for eid, adapter in self._registry._adapters.items():
            try:
                for c in adapter.advertise_capabilities():
                    caps.add(c.value if hasattr(c, "value") else str(c))
            except Exception:  # noqa: BLE001
                continue
        return sorted(caps)

    # ---- 记忆门面（B 路线：把 mem0 接成 hub 会话/长期记忆） ----------
    # 离线语义记忆回退源（与 autopilot._SEMANTIC_MEMORY_PATH 同一份文件）：
    # autopilot 经 _save_semantic_memory 写入，hub 经 memory_recall 召回，
    # 形成「写→召回」闭环，且不依赖 mem0/ollama 是否通电。
    # 单一路径真源（与 autopilot._SEMANTIC_MEMORY_PATH 同一文件，经 kernel.semantic_state）
    from kernel.semantic_state import SEMANTIC_MEMORY_PATH as _SEMANTIC_JSONL

    def memory_recall(self, query: str, user_id: str = "default",
                      **opts) -> list:
        """经 fabric 路由召回记忆（memory.semantic）。

        双后端、诚实降级：
          1. 优先走 mem0 适配器（resolve_engine 命中且有通电记忆引擎）；
          2. 若未通电记忆引擎 / mem0 调用失败 / 返回空，则回退读离线语义记忆
             _traces/semantic_memory.jsonl（autopilot 写入的同一份），用查询词做
             轻量相关度打分返回；
          3. 任何异常都返回空列表，绝不抛、不拖垮调用方。
        """
        # 1) 优先 mem0
        eid = self.resolve_engine(Capability.MEMORY_SEMANTIC.value)
        if eid:
            try:
                res = self.invoke_engine(
                    eid, Capability.MEMORY_SEMANTIC.value,
                    {"action": "search", "query": query,
                     "opts": {"user_id": user_id, **opts}},
                )
                if isinstance(res, InvokeResult) and res.ok:
                    mem = (res.data or {}).get("result") or []
                    # 仅当 mem0 返回非空 list 才采用；返回 dict/空则落 JSONL 回退
                    if isinstance(mem, list) and mem:
                        return mem
            except Exception:
                _LOG.warning("mem0 记忆召回失败，回退 JSONL", exc_info=True)
        # 2) 回退：离线语义记忆 JSONL（让「写→召回」闭环真正打通）
        return self._recall_semantic_jsonl(query, **opts)

    def _recall_semantic_jsonl(self, query: str, limit: int = 5, **opts) -> list:
        """回退召回：读离线语义记忆 jsonl，用查询词做轻量相关度打分。

        返回与 mem0 端同构的 dict 列表：
          {"text": <preview/content>, "score": <float>, "ts": ..., "task": ...}
        无文件 / 解析失败 → 空列表（不抛）。
        """
        import re
        path = self._SEMANTIC_JSONL
        if not os.path.exists(path):
            return []
        # 轻量分词：拉丁/数字词 + 中文字符（逐字），让中文部分也能做子串/字符级匹配
        q_tokens = set(re.findall(r"[a-z0-9_]+", (query or "").lower()))
        q_tokens |= set(re.findall(r"[一-鿿]", (query or "")))
        scored = []
        try:
            from kernel.semantic_state import SEMANTIC_LOCK
            with SEMANTIC_LOCK:
                with open(path, encoding="utf-8") as f:
                    raw_lines = f.readlines()
            for line in raw_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    hay = " ".join(
                        str(rec.get(k, "")) for k in ("task", "preview", "content")
                    ).lower()
                    if q_tokens:
                        overlap = sum(1 for t in q_tokens if t in hay)
                        score = overlap / len(q_tokens)
                    else:
                        score = 0.0
                    if score > 0:
                        scored.append({
                            "text": rec.get("preview") or rec.get("content") or "",
                            "score": round(score, 3),
                            "ts": rec.get("ts"),
                            "task": rec.get("task"),
                            "source": "semantic_jsonl",
                        })
        except Exception:
            _LOG.warning("回退召回语义记忆失败", exc_info=True)
            return []
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def memory_store(self, text: str, user_id: str = "default",
                     **opts) -> bool:
        """经 fabric 路由持久化记忆（memory.semantic）。

        双后端、诚实降级：
          - 优先走 mem0 适配器；
          - 未通电 / 失败 → 回退写离线语义记忆 jsonl（与 autopilot 同文件），
            保证「写→召回」闭环在无 mem0 时也成立；
          - 任何异常返回 False 不抛。
        """
        eid = self.resolve_engine(Capability.MEMORY_SEMANTIC.value)
        if eid:
            try:
                res = self.invoke_engine(
                    eid, Capability.MEMORY_SEMANTIC.value,
                    {"action": "add", "text": text,
                     "opts": {"user_id": user_id, **opts}},
                )
                if isinstance(res, InvokeResult) and res.ok:
                    return True
            except Exception:
                _LOG.warning("mem0 记忆写入失败，回退 JSONL", exc_info=True)
        # 回退：离线语义记忆 jsonl（与 autopilot._save_semantic_memory 同格式）
        return self._store_semantic_jsonl(text, **opts)

    def _store_semantic_jsonl(self, text: str, **opts) -> bool:
        """回退写入：mem0 不可用时把记忆追加到离线语义记忆 jsonl。

        与 autopilot._save_semantic_memory 同格式、同文件，保证两端互通。
        """
        import datetime
        import hashlib
        path = self._SEMANTIC_JSONL
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            content = (text or "").strip()
            if not content:
                return False
            record = {
                "ts": datetime.datetime.now().isoformat(),
                "task": (opts.get("task") or "")[:200],
                "hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "preview": content[:200].replace("\n", " "),
                "content": content[:6000],
                "bytes": len(content.encode("utf-8")),
            }
            from kernel.semantic_state import SEMANTIC_LOCK
            with SEMANTIC_LOCK:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True
        except Exception:
            _LOG.warning("回退写入语义记忆失败", exc_info=True)
            return False

    def chat(self, message: str, session_id: str = "default",
             system_prompt: str = "", max_tokens: int = 2048) -> Dict[str, Any]:
        """FabricHub 对话入口：把用户消息路由到 inference.llm 做 LLM 对话。

        FabricHub 从「能力路由器」迈出一步成为「对话中枢」——复用现有 LiteLLM
        芯粒，加载会话历史构造 chat messages，返回 LLM 文本回复。        供 /api/chat
        新开 FabricHub 路径（/api/chat 默认走此；AOS_CHAT_BACKEND 可切 kernel/brain，
        AOS_BRAIN_FALLBACK 控制 brain.py 作为 opt-in 兜底）。

        - 会话历史：经 _load_session 取最近最多 5 轮，注入 messages
        - 引擎：默认走 inference.llm 能力路由（云端优先→本地兜底，级联不写死）
        - 失败诚实返回 [FabricHub chat failed: ...]，不伪造（理念6）

        返回 {response, session_id, engine, ok}，与 brain.chat() 返回形状兼容。
        """
        try:
            # 加载最近会话历史（最多 _SESSION_MAX_TURNS 轮）
            history = _load_session(session_id)
            recent = history[-_SESSION_MAX_TURNS:] if history else []

            # 构造完整 messages 数组
            messages: List[Dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            for h in recent:
                if h.get("task"):
                    messages.append({"role": "user", "content": h["task"]})
                if h.get("response"):
                    messages.append({"role": "assistant", "content": h["response"][:2000]})
            messages.append({"role": "user", "content": message})

            # 推理路由策略（开源本地优先 → 云端兜底）：
            # - 默认走智谱直连（秒级返回，保证响应速度，CPU 环境无 GPU 时首选）
            # - AOS_LOCAL_FIRST=1 时优先尝试 Ollama 本地（数据不出本机），失败降级云端
            #   适合有 GPU 的环境跑 Qwen/DeepSeek 等开源模型
            local_first = os.environ.get("AOS_LOCAL_FIRST") == "1"

            if local_first and ollama_available():
                orc = ollama_chat(messages, max_tokens)
                if orc:
                    history.append({"task": message, "response": orc})
                    _save_session(session_id, history)
                    return {"response": orc, "session_id": session_id,
                            "engine": "ollama-local", "ok": True}

            # 云端默认：智谱直连（已验证可用，秒级返回）
            zr = zhipu_chat(messages, max_tokens)
            if zr:
                history.append({"task": message, "response": zr})
                _save_session(session_id, history)
                return {"response": zr, "session_id": session_id,
                        "engine": "zhipu-direct", "ok": True}

            # 非默认场景的兜底：若未设 local_first 但智谱失败，尝试 Ollama
            if not local_first and ollama_available():
                orc = ollama_chat(messages, max_tokens)
                if orc:
                    history.append({"task": message, "response": orc})
                    _save_session(session_id, history)
                    return {"response": orc, "session_id": session_id,
                            "engine": "ollama-local-fallback", "ok": True}

            # 路由到推理引擎（复用现有 inference.llm 芯粒，级联兜底）
            res = self.route("inference.llm", {
                "messages": messages,
                "max_tokens": max_tokens,
            })

            if isinstance(res, InvokeResult):
                if not res.ok:
                    engine = res.engine_id or "?"
                    return {"response": f"[FabricHub chat failed: {res.error}]",
                            "session_id": session_id, "engine": engine, "ok": False}
                data = res.data or {}
                # 兼容多种 LLM 返回形状：openai/agns/litellm/本地模型
                content = (data.get("text") or data.get("content")
                           or data.get("output") or "")
                if not content and "choices" in data:
                    choices = data["choices"]
                    if choices and isinstance(choices, list):
                        content = choices[0].get("message", {}).get("content", "")
                resp = str(content) if content else "[no response]"
                engine = res.engine_id or "?"
            else:
                resp = str(res)
                engine = "?"

            # 保存本轮到会话历史
            history.append({"task": message, "response": resp})
            _save_session(session_id, history)

            return {"response": resp, "session_id": session_id,
                    "engine": engine, "ok": True}
        except Exception as e:
            _LOG.warning("FabricHub.chat 失败: %s", e)
            # 末级诚实兜底：路由抛异常时同样尝试智谱直连，保证主聊天可用。
            try:
                zr = zhipu_chat(messages, max_tokens)
                if zr:
                    return {"response": zr, "session_id": session_id,
                            "engine": "zhipu-fallback", "ok": True}
            except Exception:
                pass
            return {"response": f"[FabricHub chat error: {e}]",
                    "session_id": session_id, "engine": None, "ok": False}

    def skill_discover(self, capability: str = "") -> Dict[str, Any]:
        """查询 AOS 技能生态：按能力发现对应技能（Skill 生态化入口）。

        当 capability 为空时返回所有技能的摘要；传具体能力（如 "web.search"）
        则返回声明该能力的技能列表。数据源为 skills/manifest.json（单一真相）。

        返回 {skills: [...], capability: ..., total: N}，与 route() 互补——
        查引擎用 resolve_engine，查技能用 skill_discover。
        """
        try:
            from kernel.skill_registry import get_skill_registry
            reg = get_skill_registry()
            if capability:
                skills = reg.discover(capability)
                return {"capability": capability, "skills": skills, "total": len(skills)}
            return {"skills": reg.list_all(), "total": len(reg.list_all()),
                    "summary": reg.summary()}
        except Exception as e:
            _LOG.warning("skill_discover 失败: %s", e)
            return {"skills": [], "error": str(e), "total": 0}

    def run_task(self, task: str, planner: str = "ag2", session_id: str = None,
                 reflect: bool = False, max_reflect: int = None) -> Dict[str, Any]:
        """「think→do」自主执行闭环：规划 → 解析成 steps → 编排芯粒逐跳执行。

        这是把路由器变成 agent 的关键一跃（视频观点的落地）：
          - planner != "heuristic"：优先用 resolve_engine("cognition.planning")
            找到的规划引擎（默认即 AG2 group.chat）产出文本计划，再桥接成 steps；
          - 若规划引擎不可用（无 key / 未安装 / 调用失败），**透明降级**到本地
            heuristic planner（关键词语义切分），保证端到端仍可跑；
          - 执行阶段复用 OrchestrationChiplet（system.workflow），经统一
            route() 逐跳委派，故障隔离同样生效（任一芯粒崩溃不传染整条流水线）。

        reflect=True 时启用完整反思闭环（规划→执行→质疑→重设计→再执行…），
        经 autopilot.run() 实现。autopilot 默认经本 hub 统一路由，故调用方只
        需一个入口即可获得「统一路由 + 反思闭环」的完整自主执行能力。

        返回 {task, planner, plan, steps, execution}。reflect=True 时额外含
        reflection 字段（attempts/exhausted/log）。

        注意：逻辑上分工（每步不同 capability）被保留；物理上仍是内核经统一
        route() 调度——不是自治多 Agent，正是视频反对的那类反模式我们没有。
        """
        if reflect:
            # 完整反思闭环：委托 autopilot（其 _dispatch 默认经本 hub 路由，
            # 统一路径不分裂）。函数级 import 避免模块级循环依赖。
            from kernel.autopilot import run as _autopilot_run
            kwargs = {"task": task, "planner": planner}
            if max_reflect is not None:
                kwargs["run_id"] = None  # 兼容未来扩展
            result = _autopilot_run(**kwargs)
            # 会话记录：把反思闭环结果也纳入会话上下文
            if session_id and isinstance(result, dict):
                final = (result.get("execution") or {}).get("final", "")
                if final:
                    history = _load_session(session_id)
                    history.append({"task": task, "response": str(final)[:500]})
                    _save_session(session_id, history)
            return result
        caps = self._known_capabilities()
        # B 路线记忆：执行前召回与该任务相关的历史记忆，注入流水线初始上下文
        # （下游步骤可用 in_from:"initial"/field 取用；无记忆引擎则空）。
        # 记忆召回加超时（5s），避免 mem0 在某些平台上慢初始化拖垮整个闭环。
        recalled: list = []
        if os.environ.get("AOS_TASK_MEMORY", "1") != "0":
            import threading
            result_box: list = [[]]
            def _do_recall():
                try:
                    result_box[0] = self.memory_recall(task)
                except Exception:
                    result_box[0] = []
            t = threading.Thread(target=_do_recall, daemon=True)
            t.start()
            t.join(timeout=5)
            recalled = result_box[0]
        # 会话上下文：加载历史，但不注入到 task 文本里（会污染 heuristic_plan
        # 的连词切分，导致历史文本被当成额外步骤）。改为规划后注入首步 payload。
        session_history: List[Dict[str, str]] = []
        if session_id:
            session_history = _load_session(session_id)
        initial: Dict[str, Any] = {"task": task}
        if recalled:
            initial["memory"] = recalled
        plan_text: Optional[str] = None
        steps: List[Dict[str, Any]] = []
        used_planner = planner
        planner_eid: Optional[str] = None
        if planner != "heuristic":
            planner_eid = self.resolve_engine(Capability.PLANNING.value)
            if planner_eid:
                res = self.invoke_engine(
                    planner_eid, Capability.PLANNING.value, {"topic": task}
                )
                if isinstance(res, InvokeResult) and res.ok and res.data:
                    plan_text = (res.data.get("plan") or "").strip() or None
                    if plan_text:
                        steps = parse_plan_to_steps(plan_text, caps)
        if not steps:
            steps = heuristic_plan(task, caps)
            used_planner = "heuristic"
        else:
            used_planner = planner_eid or planner
        # 会话上下文：规划完成后，把历史注入首步 payload，让 LLM 能看到之前对话。
        # 不影响规划（连词切分），只在执行时让首步 LLM 拿到完整上下文。
        if session_history and steps:
            recent = session_history[-_SESSION_MAX_TURNS:]
            history_text = "\n".join(
                f"用户: {h['task']}\n助手: {h['response'][:300]}"
                for h in recent
            )
            first_in = steps[0].get("in", {})
            original_task_text = first_in.get("task", "")
            first_in["task"] = f"{original_task_text}\n\n[之前的会话上下文]\n{history_text}"
            steps[0]["in"] = first_in
        # 执行阶段：复用统一路由层把 steps 逐跳委派给下游芯粒。
        exec_res = self.route(
            Capability.WORKFLOW_EXECUTE.value,
            {"initial": initial, "steps": steps},
        )
        if isinstance(exec_res, InvokeResult):
            # 全失败时也保留 trace（执行细节），不只留 error 字符串。
            execution = (exec_res.data if exec_res.ok
                         else {"error": exec_res.error, **(exec_res.data or {})})
        else:
            execution = exec_res
        # B 路线记忆：执行后把本次任务结果持久化（best-effort，失败不抛）。
        # 加超时（5s），避免 mem0 慢写入拖垮响应。
        stored = False
        if os.environ.get("AOS_TASK_MEMORY", "1") != "0":
            import threading
            store_box = [False]
            summary = json.dumps(
                {"task": task, "planner": used_planner,
                 "ok_steps": (execution or {}).get("ok_steps"),
                 "failed_steps": (execution or {}).get("failed_steps")},
                ensure_ascii=False,
            )
            def _do_store():
                try:
                    store_box[0] = self.memory_store(
                        f"[task] {summary}", "default")
                except Exception:
                    store_box[0] = False
            t = threading.Thread(target=_do_store, daemon=True)
            t.start()
            t.join(timeout=5)
            stored = store_box[0]
        # 最终 LLM 总结步：把所有步骤执行结果喂给 LLM，生成自然语言回答。
        # 策略：
        #   - 单步成功：直接用原始输出，跳过 LLM 总结（省 1 次 LLM 调用）
        #   - 多步或有失败：调 LLM 总结，让用户看到人话
        #   - LLM 不可用：返回原始 trace（不编造）
        response_text = ""
        if isinstance(execution, dict):
            trace = execution.get("trace", [])
            ok_count = execution.get("ok_steps", 0)
            total = len(trace)

            if ok_count == 1 and total == 1:
                # 单步成功 → 直接用输出，不调 LLM
                t = trace[0]
                out = t.get("out", "")
                if isinstance(out, dict):
                    response_text = out.get("content") or out.get("output") or ""
                else:
                    response_text = str(out) if out else ""
            elif ok_count > 0:
                # 多步 → 调 LLM 总结
                llm_eid = self.resolve_engine(Capability.LLM_GATEWAY.value)
                if llm_eid:
                    parts = []
                    for t in trace:
                        cap = t.get("capability", "?")
                        ok = t.get("ok", False)
                        out = t.get("out", "")
                        if isinstance(out, dict):
                            txt = out.get("content") or out.get("output") or ""
                        else:
                            txt = str(out) if out else ""
                        status = "成功" if ok else "失败"
                        parts.append(f"步骤[{t.get('step')}] {cap} {status}: {txt[:500]}")
                    trace_text = "\n".join(parts)
                    summary_prompt = (
                        f"用户任务: {task}\n\n"
                        f"执行结果:\n{trace_text}\n\n"
                        f"请用简洁的自然语言总结执行结果，直接回答用户的问题。"
                        f"如果代码有输出，包含输出值。不要编造未执行的内容。"
                    )
                    try:
                        llm_res = self.invoke_engine(
                            llm_eid, Capability.LLM_GATEWAY.value,
                            {"prompt": summary_prompt},
                        )
                        if isinstance(llm_res, InvokeResult) and llm_res.ok:
                            response_text = (llm_res.data or {}).get("content", "")
                    except Exception:  # noqa: BLE001
                        response_text = ""

        # 会话上下文：存储本轮对话（原始 task + 回答），供下一轮注入。
        session_turns = 0
        if session_id:
            history = _load_session(session_id)
            history.append({
                "task": task,  # 原始任务，不含注入的历史
                "response": response_text,
            })
            # 截断超长历史，只保留最近 N 轮
            if len(history) > _SESSION_MAX_TURNS:
                history = history[-_SESSION_MAX_TURNS:]
            _save_session(session_id, history)
            session_turns = len(history)
        return {
            "task": task,
            "planner": used_planner,
            "plan": plan_text,
            "steps": steps,
            "execution": execution,
            "response": response_text,  # 自然语言总结（LLM 不可用时为空）
            "memory": {"recalled": len(recalled) if recalled else 0,
                       "stored": stored},
            "session": {"id": session_id, "turns": session_turns} if session_id else None,
        }


# ── 单例工厂 ──

_hub_instance: Optional[FabricHub] = None


def get_fabric_hub() -> FabricHub:
    """获取 FabricHub 单例（完整装配实例）。

    与 build_default_kernel / aos_mcp.protocol 使用的实例一致——统一走 build_fabric_hub
    的全局装配（含编排芯粒 + 隔离引擎），消除此前「裸 FabricHub()」与「完整装配 hub」
    并存导致的多实例不一致（AutoSkill 缺失能力钩子挂在一份、/api/chat 走另一份）。

    首次调用若单例为空则构造完整装配实例；装配失败兜底回裸实例，保证不崩溃。
    """
    global _hub_instance
    if _hub_instance is None:
        try:
            from kernel.wiring import build_fabric_hub
            _hub_instance = build_fabric_hub()
        except Exception:  # noqa: BLE001 - 装配失败兜底，不阻断调用方
            _hub_instance = FabricHub()
    return _hub_instance


def set_fabric_hub(hub: "FabricHub") -> None:
    """注入/替换 FabricHub 单例（内核装配或测试时调用）。

    内核在 build_default_kernel 中构造完整装配实例后调用本函数，
    使 get_fabric_hub() 与内核共用同一实例引用（精确一致，不依赖 lru_cache 参数）。
    """
    global _hub_instance
    _hub_instance = hub


def reset_fabric_hub() -> None:
    """重置 FabricHub 单例（仅用于测试）。"""
    global _hub_instance
    _hub_instance = None
