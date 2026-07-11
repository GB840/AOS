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
        for cls in _ADAPTERS:
            try:
                self._registry.register(cls())
            except Exception as e:  # noqa: BLE001 - 单适配器故障不拖垮枢纽
                self._errors[cls.__name__] = repr(e)
                _LOG.warning("fabric 适配器注册失败 %s: %s", cls.__name__, e)

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
        """经能力路由把请求委派给首个 live 引擎；无 live 引擎返回失败结果。"""
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
