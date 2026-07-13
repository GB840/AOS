"""通用 MCP 客户端芯粒 —— 把任意外部 MCP Server 变成 AOS 的一个芯粒。

AOS 的「万物为我所用」落到协议层：任何支持 MCP (Model Context Protocol)
的服务都能通过本适配器成为 AOS 供给方。已验证支持 MCP 的 5 款真实产品
（AnySearch / ExploreYC / Sim / Auriko / Timbal）都可用同一套机制接入——
它们的 `tools` 被映射成 AOS 能力，由 FabricRegistry 统一做能力路由与
「云端用不了就本地」的运行时故障转移。

传输：MCP Streamable HTTP（JSON-RPC 2.0 over HTTP POST；响应可为
application/json 或 text/event-stream SSE）。仅用标准库，无第三方依赖。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

_LOG = logging.getLogger(__name__)

_DEFAULT_PROTOCOL = "2025-06-18"


class MCPClientAdapter(BaseAgentAdapter):
    """连接一个外部 MCP Server，把它的 tools 暴露成 AOS 能力。

    capability_map: {tool_name: Capability} —— 显式把某个 MCP tool 映射到
        AOS 能力（如 {"search_companies": Capability.DATA_QUERY}）。
        未列出的 tool 默认映射成 Capability.TOOL_USE（即「通用工具」）。
    auth_token: 可选 Bearer token（MCP Server 需要时）。
    init_on_start: 构造即 initialize + list_tools；设为 False 可延迟到首次调用。
    """

    def __init__(
        self,
        server_url: str,
        engine_id: str,
        capability_map: Optional[dict[str, Any]] = None,
        auth_token: Optional[str] = None,
        timeout: float = 10.0,
        init_on_start: bool = True,
    ) -> None:
        self._url = server_url.rstrip("/")
        self._engine_id = engine_id
        self._cap_map = capability_map or {}
        self._token = auth_token
        self._timeout = timeout
        self._tools: list[dict[str, Any]] = []
        self._healthy = False
        if init_on_start:
            self._initialize()
            self._list_tools()

    # ---- 基础契约 -------------------------------------------------
    @property
    def engine_id(self) -> str:
        return self._engine_id

    def supported_protocols(self) -> list[str]:
        return ["MCP"]

    # ---- JSON-RPC 传输（stdlib only） -----------------------------
    def _rpc(self, method: str, params: Optional[dict] = None,
             notif: bool = False) -> Optional[dict]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notif:
            payload["id"] = 1
        if params is not None:
            payload["params"] = params
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self._url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json, text/event-stream")
        if self._token:
            req.add_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:  # noqa: BLE001 - 转成干净错误
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"MCP HTTP {e.code}: {detail}") from e
        if "text/event-stream" in ctype:
            return self._parse_sse(body)
        try:
            return json.loads(body).get("result")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"MCP 非法 JSON 响应: {body[:200]}") from e

    @staticmethod
    def _parse_sse(text: str) -> Optional[dict]:
        """从 SSE 流里取最后一个含 result 的 JSON-RPC 消息。"""
        result: Optional[dict] = None
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "result" in obj:
                result = obj["result"]
        return result

    def _initialize(self) -> Optional[dict]:
        res = self._rpc(
            "initialize",
            {
                "protocolVersion": _DEFAULT_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "aos-fabric", "version": "1.0"},
            },
        )
        # MCP 要求 initialize 后发送 initialized 通知，否则部分 server 拒绝后续调用。
        try:
            self._rpc("notifications/initialized", notif=True)
        except Exception:  # noqa: BLE001 - 通知失败不致命
            pass
        self._healthy = True
        return res

    def _list_tools(self) -> list[dict[str, Any]]:
        res = self._rpc("tools/list", {})
        self._tools = (res or {}).get("tools", [])
        return self._tools

    # ---- 能力映射 -------------------------------------------------
    @staticmethod
    def _cap_to_str(cap: Any) -> str:
        return cap.value if hasattr(cap, "value") else str(cap)

    def advertise_capabilities(self) -> list[Capability]:
        caps: set[Capability] = set()
        for t in self._tools:
            mapped = self._cap_map.get(t["name"])
            if mapped is not None:
                caps.add(mapped if isinstance(mapped, Capability) else Capability(mapped))
            else:
                caps.add(Capability.TOOL_USE)
        return list(caps)

    def _tool_for_capability(self, cap: Capability) -> Optional[dict]:
        """按「有效能力」精确匹配 tool：映射过的按映射，未映射的按 TOOL_USE。

        没有 tool 的有效能力等于请求能力时，返回 None（诚实失败），绝不把
        任意能力悄悄落到第一个 tool——那是弄虚。
        """
        cap_str = self._cap_to_str(cap)
        for t in self._tools:
            mapped = self._cap_map.get(t["name"])
            eff = self._cap_to_str(mapped) if mapped is not None else Capability.TOOL_USE.value
            if eff == cap_str:
                return t
        return None

    def health(self) -> bool:
        return self._healthy and bool(self._tools)

    # ---- 执行 -----------------------------------------------------
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        tool = self._tool_for_capability(req.capability)
        if tool is None:
            return InvokeResult(
                ok=False,
                error=f"mcp[{self._engine_id}]: 无 tool 映射能力 {req.capability.value}",
            )
        try:
            res = self._rpc("tools/call", {"name": tool["name"], "arguments": req.payload})
        except Exception as e:  # noqa: BLE001 - 远端故障隔离
            return InvokeResult(
                ok=False,
                error=f"mcp[{self._engine_id}] tools/call {tool['name']} 失败: {e!r}",
            )
        if not isinstance(res, dict):
            return InvokeResult(ok=True, data={"raw": res})
        is_err = res.get("isError", False)
        content = res.get("content", []) or []
        text = "\n".join(
            c.get("text", "") for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ).strip()
        if is_err:
            return InvokeResult(ok=False, data={"raw": res}, error=text or "tool 返回错误")
        return InvokeResult(ok=True, data={"text": text, "raw": res, "tool": tool["name"]})
