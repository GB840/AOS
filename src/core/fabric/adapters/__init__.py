"""Concrete engine adapters for the AOS open fabric.

导入策略（对应项目铁律「缺依赖时跳过该插件，内核照常存活」）：
每个适配器子模块**单独** try/except 导入，任一模块导入失败（缺依赖 /
未安装 / 卡死前的报错）都只把对应名字置 None，不会让整包 import 失败，
从而拖垮 `import kernel.wiring` → FabricHub 这条链。

注意：ag2_adapter 内部对 autogen 已做惰性 + 超时守卫，本模块导入它不会卡死。
"""

try:
    from .aci_browser_adapter import BrowserUseAdapter
except Exception:  # noqa: BLE001 - 缺依赖则跳过
    BrowserUseAdapter = None

try:
    from .ag2_adapter import AG2Adapter
except Exception:  # noqa: BLE001
    AG2Adapter = None

try:
    from .agnes_adapter import AgnesAdapter
except Exception:  # noqa: BLE001
    AgnesAdapter = None

try:
    from .code_execution_adapter import CodeExecutionAdapter
except Exception:  # noqa: BLE001
    CodeExecutionAdapter = None

try:
    from .file_adapter import FileAdapter
except Exception:  # noqa: BLE001
    FileAdapter = None

try:
    from .litellm_adapter import LiteLLMAdapter
except Exception:  # noqa: BLE001
    LiteLLMAdapter = None

try:
    from .mcp_client_adapter import MCPClientAdapter
except Exception:  # noqa: BLE001
    MCPClientAdapter = None

try:
    from .mcp_stdio_adapter import MCPStdioAdapter
except Exception:  # noqa: BLE001
    MCPStdioAdapter = None

try:
    from .mem0_adapter import Mem0Adapter
except Exception:  # noqa: BLE001
    Mem0Adapter = None

try:
    from .observability_langfuse_adapter import LangfuseAdapter
except Exception:  # noqa: BLE001
    LangfuseAdapter = None

try:
    from .openclaw_adapter import OpenClawAdapter
except Exception:  # noqa: BLE001
    OpenClawAdapter = None

try:
    from .search_adapter import SearchAdapter
except Exception:  # noqa: BLE001
    SearchAdapter = None

try:
    from .web_fetch_adapter import WebFetchAdapter
except Exception:  # noqa: BLE001
    WebFetchAdapter = None

try:
    from .crawl4ai_adapter import Crawl4AIAdapter
except Exception:  # noqa: BLE001 - 缺依赖（crawl4ai）则跳过，不拖垮内核
    Crawl4AIAdapter = None

try:
    from .media_gen_adapter import MediaGenAdapter
except Exception:  # noqa: BLE001 - 零依赖；导入失败也置 None，不拖垮内核
    MediaGenAdapter = None

try:
    from .threejs_adapter import ThreejsAdapter
except Exception:  # noqa: BLE001
    ThreejsAdapter = None

try:
    from .stt_adapter import STTAdapter
except Exception:  # noqa: BLE001
    STTAdapter = None

try:
    from .tts_adapter import TTSAdapter
except Exception:  # noqa: BLE001
    TTSAdapter = None

try:
    from .lnn_adapter import LNNAdapter
except Exception:  # noqa: BLE001
    LNNAdapter = None

try:
    from .lfm_adapter import LFMAdapter
except Exception:  # noqa: BLE001
    LFMAdapter = None

try:
    from .scripts_adapter import ScriptsAdapter
except Exception:  # noqa: BLE001
    ScriptsAdapter = None

try:
    from .omni_minicpm_adapter import MiniCPMOAdapter
except Exception:  # noqa: BLE001 - 缺依赖（websockets）则跳过，不拖垮内核
    MiniCPMOAdapter = None

try:
    from .vlm_adapter import VLMAdapter
except Exception:  # noqa: BLE001 - 缺依赖则跳过，不拖垮内核
    VLMAdapter = None

try:
    from .video_maker_adapter import VideoMakerAdapter
except Exception:  # noqa: BLE001
    VideoMakerAdapter = None

try:
    from .remotion_adapter import RemotionAdapter
except Exception:  # noqa: BLE001
    RemotionAdapter = None

try:
    from .security_audit_adapter import SecurityAuditAdapter
except Exception:  # noqa: BLE001 - 缺依赖则跳过，不拖垮内核
    SecurityAuditAdapter = None

try:
    from .ida_pro_mcp_adapter import IdaProMcpAdapter
except Exception:  # noqa: BLE001 - 缺依赖则跳过，不拖垮内核
    IdaProMcpAdapter = None

# 内容飞轮 4 个适配器：fabric_hub.py 也单独 `from .xxx_adapter import` 注册，
# 这里补做统一入口导出（TD-10），方便外部代码（测试 / 文档生成 / 健康检查）
# 用 `from core.fabric.adapters import XxxAdapter` 一行拿到。
try:
    from .content_marketer_adapter import ContentMarketerAdapter
except Exception:  # noqa: BLE001
    ContentMarketerAdapter = None

try:
    from .cast_adapter import CastAdapter
except Exception:  # noqa: BLE001
    CastAdapter = None

try:
    from .echo_adapter import EchoAdapter
except Exception:  # noqa: BLE001
    EchoAdapter = None

try:
    from .refine_adapter import RefineAdapter
except Exception:  # noqa: BLE001
    RefineAdapter = None

try:
    from .refinery_adapter import RefineryAdapter
except Exception:  # noqa: BLE001
    RefineryAdapter = None

try:
    from .img2threejs_adapter import Img2ThreejsAdapter
except Exception:  # noqa: BLE001 - vendored 脚本缺失则跳过，不拖垮内核
    Img2ThreejsAdapter = None

try:
    from .mediakit_adapter import MediakitAdapter
except Exception:  # noqa: BLE001 - 缺依赖（理论零依赖；CLI 未装则 health=False）则跳过，不拖垮内核
    MediakitAdapter = None

try:
    from .knowmesh_adapter import KnowmeshAdapter
except Exception:  # noqa: BLE001 - 零依赖（仅 stdlib urllib）；服务未起则 health=False，不拖垮内核
    KnowmeshAdapter = None

try:
    from .vosk_backend import VoskSTT
except Exception:  # noqa: BLE001 - 缺 vosk 则跳过，不拖垮内核
    VoskSTT = None

try:
    from .video_shotcraft_backend import VideoShotcraft
except Exception:  # noqa: BLE001 - 零依赖（stdlib）；仓库/node 缺失则 health=False，不拖垮内核
    VideoShotcraft = None

try:
    from .localai_backend import LocalAIBackend
except Exception:  # noqa: BLE001 - 缺 requests 则跳过，不拖垮内核
    LocalAIBackend = None

try:
    from .piper_backend import PiperTTS
except Exception:  # noqa: BLE001 - 缺 piper 则跳过，不拖垮内核
    PiperTTS = None

try:
    from .constitutional_governor import ConstitutionalGovernor
except Exception:  # noqa: BLE001 - 缺 constitutional-agent 则跳过，不拖垮内核
    ConstitutionalGovernor = None

__all__ = [
    n for n in (
        "AG2Adapter",
        "AgnesAdapter",
        "BrowserUseAdapter",
        "CastAdapter",
        "CodeExecutionAdapter",
        "ContentMarketerAdapter",
        "EchoAdapter",
        "FileAdapter",
        "LangfuseAdapter",
        "LiteLLMAdapter",
        "LFMAdapter",
        "MCPClientAdapter",
        "MCPStdioAdapter",
        "Mem0Adapter",
        "OpenClawAdapter",
        "RefineAdapter",
        "RefineryAdapter",
        "SearchAdapter",
        "WebFetchAdapter",
        "Crawl4AIAdapter",
        "MediaGenAdapter",
        "ThreejsAdapter",
        "STTAdapter",
        "TTSAdapter",
        "IdaProMcpAdapter",
        "LNNAdapter",
        "ScriptsAdapter",
        "MiniCPMOAdapter",
        "VLMAdapter",
        "VideoMakerAdapter",
        "RemotionAdapter",
        "SecurityAuditAdapter",
        "Img2ThreejsAdapter",
        "KnowmeshAdapter",
        "MediakitAdapter",
        "VoskSTT",
        "VideoShotcraft",
        "LocalAIBackend",
        "PiperTTS",
        "ConstitutionalGovernor",
    )
    if globals().get(n) is not None
]
