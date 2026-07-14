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
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.fabric import FabricRegistry
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
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
    ThreejsAdapter,
    STTAdapter,
    TTSAdapter,
    LNNAdapter,
    LFMAdapter,
    ScriptsAdapter,
)
from core.fabric.capability import Capability
from kernel.isolation.subprocess_iso import IsolatedEngineHost
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet
from kernel.plugins.plan_bridge import heuristic_plan, parse_plan_to_steps

_LOG = logging.getLogger("aos.fabric.hub")

# 会话上下文存储（进程内缓存 + 磁盘持久化）。
# key=session_id, value=[{"task": "...", "response": "..."}, ...]
# 设计：内存缓存提速热会话；磁盘 JSON 落盘让 CLI 跨进程也能记住对话。
# 每个会话最多保留最近 5 轮，避免无限增长拖慢上下文注入。
_SESSIONS: Dict[str, List[Dict[str, str]]] = {}
_SESSION_MAX_TURNS = 5
_SESSION_DIR = Path("data/workspaces/fabric/sessions")


def _session_path(session_id: str) -> Path:
    return _SESSION_DIR / f"{session_id}.json"


def _load_session(session_id: str) -> List[Dict[str, str]]:
    """加载会话历史：先查内存缓存，没有再读磁盘。"""
    if session_id in _SESSIONS:
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
    _SESSIONS[session_id] = history
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
        AgnesAdapter,        # OpenAI-compatible 多模态平面：文本/图像/视频（需 AGNES_API_KEY）
        CodeExecutionAdapter,  # 本地沙箱代码执行（subprocess 隔离，零依赖）
        FileAdapter,           # 文件读写（workspace 内，路径遍历防护）
        ThreejsAdapter,       # 交互式 3D 场景生成（MEDIA_3D，浏览器端渲染）
        STTAdapter,           # 语音识别（VOICE_STT：whisper.cpp/faster-whisper/Web Speech）
        TTSAdapter,           # 语音合成（VOICE_TTS：kokoro/edge-tts/XTTS/Web Speech）
        LNNAdapter,           # 液态神经网络时间序列推理（INFERENCE_LNN，纯 numpy 自包含）
        LFMAdapter,           # LFM2 轻量 LLM 供给方（inference.llm 的「低功耗」一极，高低搭配）
        ScriptsAdapter,       # 动态脚本执行（scripts/repls/*.py 热加载）
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

    def __init__(self, adapters: Optional[tuple] = None) -> None:
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
        self._registry = FabricRegistry()
        self._errors: Dict[str, str] = {}
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
        # codebase-memory-mcp 是 stdio-only 的 MCP server（纯 C / 零依赖 / MIT），
        # 现有 register_mcp_server 只接 HTTP(SSE)，接不上它。这里单独接 stdio
        # 传输，并把真实工具「弄进」AOS：二进制缺失时优雅跳过，绝不谎报 live。
        self._register_env_codebase_mcp()
        # 默认通电编排芯粒：让 system.workflow 能力在构建后即 live，
        # run_task 的底层编排才不会因「no live provider」空转。
        # （之前只有显式 add_orchestrator() 才挂，health_report 里
        #  system.workflow 永远显示未通电，run_task 默认跑不出编排。）
        try:
            self.add_orchestrator()
        except Exception as e:  # noqa: BLE001 - 编排芯粒注册失败不拖垮枢纽
            _LOG.warning("默认注册编排芯粒失败: %s", e)
        # 后台预热重型依赖（autogen 80s / litellm 22s import），避免 health/
        # 初始化被卡死。预热期间 guarded_import 命中 _WARMING 直接返回 None，
        # health 如实标 dead，预热线程完成后再标 live，全程不阻塞调用方。
        try:
            from ..resilience import prewarm
            prewarm(["autogen", "litellm", "mem0ai", "mem0"])
        except Exception:  # noqa: BLE001
            pass

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
        req = InvokeRequest(capability=capability, payload=payload, trace_id=trace_id)
        providers = self._registry.providers_for(req.capability)
        if not providers:
            return InvokeResult(ok=False, error=f"no live provider for {capability}")
        last_res: InvokeResult | None = None
        attempts: list[str] = []
        for adapter in providers:
            try:
                res = adapter.invoke(req)
            except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
                eid = adapter.engine_id
                self._failures[eid] = time.perf_counter()
                self._errors[eid] = f"invoke failed: {e!r}"
                _LOG.warning("fabric 芯粒 %s invoke 异常已隔离: %s", eid, e)
                attempts.append(f"{eid} raised: {e!r}")
                continue
            if res.ok:
                return res
            eid = adapter.engine_id
            self._failures[eid] = time.perf_counter()
            self._errors[eid] = res.error or "ok=False"
            attempts.append(f"{eid}: {res.error}")
            last_res = res
        # 全部失败：返回最后一个芯粒的真实结果（保留其 data，如编排 trace/
        # ok_steps），错误附注「已协商 N 个芯粒」以体现端云合作耗尽，而非合成
        # data=None 把下游有用的失败上下文吞掉。
        if last_res is not None:
            return InvokeResult(
                ok=False,
                data=last_res.data,
                error=f"all providers failed [{capability}] "
                      f"after {len(attempts)} attempt(s): " + " | ".join(attempts),
            )
        return InvokeResult(
            ok=False,
            error=f"all providers raised [{capability}]: " + " | ".join(attempts),
        )

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
                            task_us: float = 0.0, standby: bool = True) -> str:
        """把一个真实适配器**隔离进独立子进程**，作为 fabric 引擎注册。

        这是 Day22-30 B 路线「收口进生产」的落点：
          - 该引擎的 invoke / health 全部在子进程内执行，崩溃不传染宿主内核；
          - recover(eid) 默认走热备切换（毫秒级，过 3s 恢复闸门，见
            IsolatedEngineHost.standby），无热备时回退冷启动 kill+respawn；
          - 能力路由/自检逻辑复用现有 route()/resolve_engine()/health_report()，
            零改动（注册的是 IsolatedAdapterProxy）。
        默认 transport 取 AOS_ISO_TRANSPORT（沙箱=tcp，生产=pipe/Named Pipe）。
        """
        caps = list(adapter_cls().advertise_capabilities())
        spec = f"{adapter_cls.__module__}:{adapter_cls.__qualname__}"
        host = IsolatedEngineHost(engine_id, spec, transport=transport,
                                  task_us=task_us, standby=standby)
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
    def memory_recall(self, query: str, user_id: str = "default",
                      **opts) -> list:
        """经 fabric 路由召回记忆（memory.semantic）。

        无通电记忆引擎 / 引擎调用失败 → 返回空列表（绝不抛，不拖垮调用方）。
        这是「任务间记住偏好」的读取端。
        """
        eid = self.resolve_engine(Capability.MEMORY_SEMANTIC.value)
        if not eid:
            return []
        res = self.invoke_engine(
            eid, Capability.MEMORY_SEMANTIC.value,
            {"action": "search", "query": query,
             "opts": {"user_id": user_id, **opts}},
        )
        if isinstance(res, InvokeResult) and res.ok:
            return (res.data or {}).get("result") or []
        return []

    def memory_store(self, text: str, user_id: str = "default",
                     **opts) -> bool:
        """经 fabric 路由持久化记忆（memory.semantic）。

        无通电记忆引擎 / 引擎调用失败（如缺 LLM key）→ 干净返回 False 不抛。
        这是「任务间记住偏好」的写入端。
        """
        eid = self.resolve_engine(Capability.MEMORY_SEMANTIC.value)
        if not eid:
            return False
        res = self.invoke_engine(
            eid, Capability.MEMORY_SEMANTIC.value,
            {"action": "add", "text": text,
             "opts": {"user_id": user_id, **opts}},
        )
        return isinstance(res, InvokeResult) and res.ok

    def run_task(self, task: str, planner: str = "ag2", session_id: str = None) -> Dict[str, Any]:
        """「think→do」自主执行闭环：规划 → 解析成 steps → 编排芯粒逐跳执行。

        这是把路由器变成 agent 的关键一跃（视频观点的落地）：
          - planner != "heuristic"：优先用 resolve_engine("cognition.planning")
            找到的规划引擎（默认即 AG2 group.chat）产出文本计划，再桥接成 steps；
          - 若规划引擎不可用（无 key / 未安装 / 调用失败），**透明降级**到本地
            heuristic planner（关键词语义切分），保证端到端仍可跑；
          - 执行阶段复用 OrchestrationChiplet（system.workflow），经统一
            route() 逐跳委派，故障隔离同样生效（任一芯粒崩溃不传染整条流水线）。

        返回 {task, planner, plan, steps, execution}。

        注意：逻辑上分工（每步不同 capability）被保留；物理上仍是内核经统一
        route() 调度——不是自治多 Agent，正是视频反对的那类反模式我们没有。
        """
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
