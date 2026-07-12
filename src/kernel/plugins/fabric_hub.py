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
import time
from typing import Any, Dict, List, Optional

from core.fabric import FabricRegistry
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.adapters import (
    AG2Adapter,
    AgnesAdapter,
    BrowserUseAdapter,
    LangfuseAdapter,
    LiteLLMAdapter,
    Mem0Adapter,
    OpenClawAdapter,
)
from kernel.isolation.subprocess_iso import IsolatedEngineHost
from kernel.plugins.orchestration_chiplet import OrchestrationChiplet

_LOG = logging.getLogger("aos.fabric.hub")


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
_ADAPTERS: tuple[type[BaseAgentAdapter], ...] = (
    OpenClawAdapter,
    AG2Adapter,
    LiteLLMAdapter,
    Mem0Adapter,
    BrowserUseAdapter,
    LangfuseAdapter,
    AgnesAdapter,   # OpenAI-compatible 多模态平面：文本/图像/视频（需 AGNES_API_KEY）
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
            try:
                self._registry.register(cls())
            except Exception as e:  # noqa: BLE001 - 单适配器故障不拖垮枢纽
                self._errors[cls.__name__] = repr(e)
                _LOG.warning("fabric 适配器注册失败 %s: %s", cls.__name__, e)

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
        """经能力路由把请求委派给首个 live 引擎；无 live 引擎返回失败结果。

        异常隔离：任一芯粒 invoke 抛异常都会被单独捕获，返回干净的
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
        adapter = providers[0]
        try:
            return adapter.invoke(req)
        except Exception as e:  # noqa: BLE001 - 芯粒崩溃隔离，不传染
            eid = adapter.engine_id
            self._failures[eid] = time.perf_counter()
            self._errors[eid] = f"invoke failed: {e!r}"
            _LOG.warning("fabric 芯粒 %s invoke 异常已隔离: %s", eid, e)
            return InvokeResult(ok=False, error=f"{eid} invoke failed: {e!r}")

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
