"""本机 IDA Pro 逆向工程 MCP 适配器（re.ida 平面）。

把 mrexodia/ida-pro-mcp（真实开源，MIT，GitHub 546 commits，2026-06 增长最快的
安全项目之一）接入 AOS 供给面，落实「万物为我所用」。它通过 MCP 协议把**你本机
运行的 IDA Pro** 连到 LLM，让 AI 能反编译 / 重命名 / 加注释 / 查交叉引用。

红线（对应理念5「权限即边界」+ 理念6/9「诚实可验证」+ 内容策略）：
1. **仅连接 localhost 的 ida-pro-mcp server**（即你自己机器上的 IDA 实例）。
   任何非本机 URL 一律诚实拒绝——绝不连别人的 IDA、绝不碰你无权分析的二进制。
2. **只做静态/只读分析**（反编译、列函数、查字符串、给自有的 IDB 加注释），
   **永久拒绝**调试器类「unsafe」工具（`dbg_*`）。这些工具由 IDA 侧 `?ext=dbg`
   启用（非 `--unsafe` 启动标志），需 IDA Pro 调试器许可 + 一个运行中的调试会话，
   开销与风险远高于静态分析——最高危 `dbg_write` 可 corrupt 进程内存、`py_eval`
   可凭任意 Python 代码损坏 IDB。详见 `explain_unsafe_tools()` 与 `docs/AOS_IDA_PRO_MCP.md`。
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
_LOCALHOST_HOSTS = ("localhost", "127.0.0.1", "::1")

# D3：写操作需显式 opt-in（payload read_only=False）才放行；调试类 unsafe 工具永远拒绝。
_WRITE_TOOLS = frozenset({
    "rename", "rename_global", "comment", "set_comment",
    "set_function_prototype", "set_local_variable_name",
    "set_struct_member_name", "add_struct", "add_enum",
})
_UNSAFE_PREFIX = "dbg_"

# D3：调试类 unsafe 工具（dbg_*）永久拒绝。这些工具由 IDA 侧 `?ext=dbg` 启用，
# 需要 IDA Pro 调试器许可 + 一个运行中的调试会话，开销与风险远高于静态分析。
# 下表逐类列出开销与风险，供 `explain_unsafe_tools()` 与上層审计查询。
# 数据来源：mrexodia/ida-pro-mcp README（GitHub，MIT，2026-06 核实）。
_UNSAFE_TOOLS_RISK = {
    "control": {
        "tools": ["dbg_start", "dbg_exit", "dbg_continue", "dbg_run_to",
                  "dbg_step_into", "dbg_step_over"],
        "cost": "需启动/附加调试器，占用 IDA 调试会话与系统进程；失败可能遗留僵尸进程",
        "risk": "高：错误地址/断点可致被调试进程崩溃或调试状态不一致",
    },
    "breakpoint": {
        "tools": ["dbg_bps", "dbg_add_bp", "dbg_delete_bp", "dbg_toggle_bp"],
        "cost": "依赖调试会话；误配致频繁 SIGTRAP 拖慢目标",
        "risk": "中：误删/误加断点错过分析时机",
    },
    "memory_write": {
        "tools": ["dbg_write"],
        "cost": "需调试会话；直接写入目标进程内存",
        "risk": "极高：写错地址/数据可 corrupt 进程内存、改变执行流、造成崩溃",
    },
    "read_only": {
        "tools": ["dbg_regs", "dbg_regs_all", "dbg_regs_remote", "dbg_gpregs",
                  "dbg_gpregs_remote", "dbg_regs_named", "dbg_regs_named_remote",
                  "dbg_stacktrace", "dbg_read"],
        "cost": "需调试会话；纯读取",
        "risk": "低：只读，但依赖会话稳定性",
    },
    # 非 dbg_ 前缀但同样危险的工具（IDA 上下文执行任意 Python / 修改数据库）
    "arbitrary_code": {
        "tools": ["py_eval"],
        "cost": "在 IDA 进程内执行任意 Python；可调用全部 IDA 内部 API",
        "risk": "极高：可凭任意代码损坏 IDB、篡改反汇编、植入脚本",
    },
}


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

    @property
    def engine_id(self) -> str:
        return "ida-pro-mcp"

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

    @classmethod
    def explain_unsafe_tools(cls) -> dict:
        """返回调试类 unsafe 工具的开销/风险说明（供上层审计、用户自查、测试断言）。

        为什么存在：红线「永久拒绝 dbg_*」必须可解释——用户/审计方应能查到
        「到底拒了什么、为什么拒、开销多高、风险多大」，而非一句「不安全」黑箱拒绝
        （对应理念6/9 诚实可验证）。返回结构是 `_UNSAFE_TOOLS_RISK` 的副本。
        """
        return dict(_UNSAFE_TOOLS_RISK)

    def health(self) -> bool:
        # 候选资格 = 配置了本机(localhost) URL。真实连通性延后到 invoke 时做
        # 握手（故障隔离、不传染）；_healthy 仅作「最近一次握手是否成功」的信息
        # 性标志，不阻断候选资格——否则「注册了但还没连过」的适配器永远进不了
        # providers_for，route 便无从触发首次握手（死锁）。非 localhost 一律 False（红线）。
        return bool(self._url) and self.is_localhost

    # ---- 执行 -----------------------------------------------------
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        # D3 红线纵深：每次调用入口再校验 localhost（注册时校验不够，防运行时 url 漂移）。
        if not self.is_localhost:
            return InvokeResult(
                ok=False,
                error="ida-pro-mcp 仅允许连接 localhost（你自己的 IDA 实例）；"
                      "拒绝非本机 URL，避免触碰你无权分析的第三方目标。",
            )
        payload = req.payload or {}
        tool = payload.get("tool") or payload.get("name") or "get_metadata"
        # D3：调试类 unsafe 工具（dbg_*）永远拒绝，即便显式 opt-in 也不放行。
        if tool.startswith(_UNSAFE_PREFIX):
            return InvokeResult(
                ok=False,
                error=f"ida-pro-mcp 拒绝调试类 unsafe 工具 {tool!r}（红线：默认且永久不触发调试器）",
                data={
                    "tool": tool,
                    "blocked_reason": "unsafe_debug_tool",
                    "unsafe_risk_summary": (
                        "dbg_* 需 IDA 侧 ?ext=dbg 启用（非 --unsafe 标志），"
                        "要求 IDA Pro 调试器 + 运行中的调试会话；最高危 dbg_write 可 corrupt "
                        "进程内存，控制类可崩溃进程。详见 explain_unsafe_tools() / docs/AOS_IDA_PRO_MCP.md"
                    ),
                },
            )
        # D3：默认只读（read_only=True）；写操作（rename/comment/...）需显式 read_only=False。
        read_only = payload.get("read_only", True)
        if tool in _WRITE_TOOLS and read_only:
            return InvokeResult(
                ok=False,
                error=f"写操作 {tool!r} 需显式 payload read_only=False 才能执行（默认只读红线）",
                data={"tool": tool, "blocked_reason": "read_only_default"},
            )
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
            return InvokeResult(ok=True, data={"raw": res, "read_only": read_only})
        is_err = res.get("isError", False)
        content = res.get("content", []) or []
        text = "\n".join(
            c.get("text", "") for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ).strip()
        if is_err:
            return InvokeResult(ok=False, data={"raw": res, "tool": tool, "read_only": read_only},
                                error=text or "ida-pro-mcp 工具返回错误")
        return InvokeResult(ok=True, data={"text": text, "raw": res, "tool": tool, "read_only": read_only})
