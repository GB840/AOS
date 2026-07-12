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
from core.fabric.adapter import BaseAgentAdapter, InvokeRequest
from core.fabric.adapters import (
    AG2Adapter,
    BrowserUseAdapter,
    LangfuseAdapter,
    LiteLLMAdapter,
    Mem0Adapter,
    OpenClawAdapter,
)

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
)


class FabricHub:
    """能力路由枢纽：按 Capability 把任务委派给 live 的真实 OSS 引擎。"""

    def __init__(self) -> None:
        self._registry = FabricRegistry()
        self._errors: Dict[str, str] = {}
        # 模拟路由层延迟（μs）：默认 0（生产零影响）。
        # 探测时由 scripts/ipc_probe.py 通过 set_route_sim_us() 打开，
        # 用于测量「内核↔芯粒」这一跳的 IPC 开销是否 ≤5%（Day8-10 闸门）。
        self.route_sim_us: float = float(os.environ.get("ROUTE_SIM_US", "0") or "0")
        for cls in _ADAPTERS:
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

        若 route_sim_us>0，则在委派前 sleep 该微秒数，模拟内核↔芯粒这一跳的
        IPC 延迟（Named Pipe ~20μs），供 ipc_probe 测量开销占比。
        """
        if self.route_sim_us:
            _busy_wait(self.route_sim_us / 1_000_000.0)
        return self._registry.route(
            InvokeRequest(capability=capability, payload=payload, trace_id=trace_id)
        )

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
            }
            report["total"] += 1
            if live:
                report["live"] += 1
        report["registration_errors"] = dict(self._errors)
        return report

    def advertised(self) -> Dict[str, List[str]]:
        """快照：引擎 id -> 它声明的能力列表。"""
        return self._registry.snapshot()
