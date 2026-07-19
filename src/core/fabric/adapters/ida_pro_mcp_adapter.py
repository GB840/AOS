"""本机 IDA Pro 逆向工程 MCP 适配器（re.ida 平面）。

把 mrexodia/ida-pro-mcp（真实开源，MIT，GitHub 546 commits，2026-06 增长最快的
安全项目之一）接入 AOS 供给面，落实「万物为我所用」。它通过 MCP 协议把**你本机
运行的 IDA Pro** 连到 LLM，让 AI 能反编译 / 重命名 / 加注释 / 查交叉引用。

红线（对应理念5「权限即边界」+ 理念6/9「诚实可验证」+ 内容策略）：
1. **仅连接 localhost 的 ida-pro-mcp server**（即你自己机器上的 IDA 实例）。
   任何非本机 URL 一律诚实拒绝——绝不连别人的 IDA、绝不碰你无权分析的二进制。
2. **只做静态/只读分析**（反编译、列函数、查字符串、给自有的 IDB 加注释），
   默认不触发调试器类「unsafe」工具（需显式 tool=dbg_* 且你自担风险）。
3. **你负责确保对加载进 IDA 的二进制有合法分析权**（你自己的程序 / 已授权审计 /
   开源软件）。本适配器不判断二进制来源，但任何对外/对第三方目标的用途都越界。

接入方式（用户主机，沙箱无法跑 IDA）：
  pip install --upgrade git+https://github.com/mrexodia/ida-pro-mcp
  ida-pro-mcp --install          # 安装 IDA 插件
  启动 IDA 并加载目标二进制（.idb/.i64）
  设 IDA_PRO_MCP_URL=http://localhost:<port>/mcp
AOS 侧：FabricHub 在 IDA_PRO_MCP_URL 存在且为 localhost 时自动注册 re.ida 芯粒。
传输仅用标准库（urllib + JSON-RPC 2.0），无第三方依赖。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)
_DEFAULT_PROTOCOL = "2025-06-18"
_LOCALHOST_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _host_of(url: str) -> str:
    """从 URL 里抠出 host（小写），供 localhost 校验。"""
    if not url:
        return ""
    after = url.split("://", 1)[-1]
    authority = after.split("/", 1)[0]
    return authority.split(":", 1)[0].lower()


class IdaProMcpAdapter(BaseAgentAdapter):
    """连接本机 ida-pro-mcp server，把 IDA 的逆向工具暴露成 AOS 的 re.ida 能力。

    transport_fn：测试可注入伪造 server 响应；默认走真实 HTTP JSON-RPC。
    """

    engine_id = "ida-pro-mcp"

    def __init__(
        self,
        server_url: Optional[str] = None,
        engine_id: str = "ida-pro-mcp",
        auth_token: Optional[str] = None,
        timeout: float = 15.0,
        init_on_start: bool = False,
        transport_fn: Optional[Callable[..., Optional[dict]]] = None,
    ) -> None:
        self._url = (server_url or "").rstrip("/")
        self._engine_id = engine_id
        self._token = auth_token
        self._timeout = timeout
        self._tools: list[dict[str, Any]] = []
        self._healthy = False
        self._initialized = False
        self._transport = transport_fn or self._http_rpc
        if init_on_start:
            self._initialize()
            self._list_tools()

    # ---- 红线：仅 localhost ----------------------------------------
    @property
    def is_localhost(self) -> bool:
        host = _host_of(self._url)
        return host in _LOCALHOST_HOSTS or host.endswith(".localhost")

    # ---- JSON-RPC 传输（stdlib only，复用 MCPClientAdapter 原语） -----
    def _http_rpc(self, method: str, params: Optional[dict] = None,
                  notif: bool = False) -> Optional[dict]:
        if not self.is_localhost:
            raise RuntimeError("ida-pro-mcp 仅允许连接 localhost（你自己的 IDA 实例）")
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
        except urllib.error.HTTPError as e:  # noqa: BLE001 - 转干净错误
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(f"ida-pro-mcp HTTP {e.code}: {detail}") from e
        if "text/event-stream" in ctype:
            return self._parse_sse(body)
        try:
            return json.loads(body).get("result")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"ida-pro-mcp 非法 JSON 响应: {body[:200]}") from e

    @staticmethod
    def _parse_sse(text: str) -> Optional[dict]:
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
        if not self.is_localhost:
            raise RuntimeError("ida-pro-mcp 仅允许连接 localhost（你自己的 IDA 实例）")
        res = self._transport(
            "initialize",
            {
                "protocolVersion": _DEFAULT_PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "aos-fabric", "version": "1.0"},
            },
        )
        try:
            self._transport("notifications/initialized", notif=True)
        except Exception:  # noqa: BLE001 - 通知失败不致命
            pass
        self._initialized = True
        self._healthy = True
        return res

    def _list_tools(self) -> list[dict[str, Any]]:
        res = self._transport("tools/list", {})
        self._tools = (res or {}).get("tools", [])
        return self._tools

    # ---- 能力契约 -------------------------------------------------
    def advertise_capabilities(self) -> list[Capability]:
        # 单一逆向工程能力；具体工具由 payload["tool"] 指定。
        return [Capability.RE_IDA]

    def health(self) -> bool:
        # 候选资格 = 配置了本机(localhost) URL。真实连通性延后到 invoke 时做
        # 握手（故障隔离、不传染）；_healthy 仅作「最近一次握手是否成功」的信息
        # 性标志，不阻断候选资格——否则「注册了但还没连过」的适配器永远进不了
        # providers_for，route 便无从触发首次握手（死锁）。非 localhost 一律 False（红线）。
        return bool(self._url) and self.is_localhost

    # ---- 执行 -----------------------------------------------------
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self.is_localhost:
            return InvokeResult(
                ok=False,
                error="ida-pro-mcp 仅允许连接 localhost（你自己的 IDA 实例）；"
                      "拒绝非本机 URL，避免触碰你无权分析的第三方目标。",
            )
        payload = req.payload or {}
        tool = payload.get("tool") or payload.get("name") or "get_metadata"
        arguments = payload.get("arguments", payload.get("params", {}))
        try:
            if not self._initialized:
                self._initialize()
                self._list_tools()
            res = self._transport("tools/call", {"name": tool, "arguments": arguments})
        except Exception as e:  # noqa: BLE001 - 远端故障隔离
            return InvokeResult(
                ok=False,
                error=f"ida-pro-mcp tools/call {tool} 失败: {e!r}",
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
            return InvokeResult(ok=False, data={"raw": res, "tool": tool},
                                error=text or "ida-pro-mcp 工具返回错误")
        return InvokeResult(ok=True, data={"text": text, "raw": res, "tool": tool})
