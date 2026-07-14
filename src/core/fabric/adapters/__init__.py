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

__all__ = [
    n for n in (
        "AG2Adapter",
        "AgnesAdapter",
        "BrowserUseAdapter",
        "CodeExecutionAdapter",
        "FileAdapter",
        "LangfuseAdapter",
        "LiteLLMAdapter",
        "LFMAdapter",
        "MCPClientAdapter",
        "MCPStdioAdapter",
        "Mem0Adapter",
        "OpenClawAdapter",
        "SearchAdapter",
        "WebFetchAdapter",
        "ThreejsAdapter",
        "STTAdapter",
        "TTSAdapter",
        "LNNAdapter",
        "ScriptsAdapter",
        "MiniCPMOAdapter",
    )
    if globals().get(n) is not None
]
