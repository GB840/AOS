"""stdio MCP 客户端芯粒 —— 把任意 stdio-only 的 MCP Server 变成 AOS 芯粒。

真实用例：codebase-memory-mcp（DeusData，纯 C / 零依赖 / MIT，158 种语言
tree-sitter）是一个 **MCP stdio server**——通过 stdin/stdout 走 JSON-RPC 2.0，
日志走 stderr。AOS 既有的 mcp_client_adapter 只接 HTTP(SSE)，接不上它。本适配
器补上 stdio 传输，让这类「本地单二进制」MCP 工具也能成为 AOS 供给方（例如
code.understanding 能力），落实「万物为我所用 / 把真实开源工具弄进 AOS」。

传输细节（严格按 MCP stdio 约定）：
- 用 subprocess 起 server（cwd 可配，便于把仓库目录喂给它索引）；
- 行分隔 JSON-RPC：写一行请求到 stdin、读一行响应到 stdout；
- 必须先 initialize 握手，再发 notifications/initialized，否则 server 拒后续调用；
- server 日志走 stderr（已重定向到 DEVNULL，绝不污染协议流）；
- 二进制缺失 / 启动失败 / 握手超时：构造即优雅失败，health() 恒为 False，
  绝不谎报 live（与 FabricHub「诚实通电自检」铁律一致）。

仅用标准库（subprocess / json / threading），无第三方依赖。同步对话（AOS 是
同步 invoke），用锁串行化，避免请求/响应交错。
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
from typing import Any, Optional

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

_LOG = logging.getLogger(__name__)
_DEFAULT_PROTOCOL = "2025-06-18"


class MCPStdioAdapter(BaseAgentAdapter):
    """连接一个 stdio MCP Server（子进程），把它的 tools 暴露成 AOS 能力。

    command: 启动 server 的命令（如 ["codebase-memory-mcp"] 或二进制绝对路径）。
    args: 附加命令行参数（如 ["--ui=false"]）。
    cwd: 子进程工作目录（codebase-memory-mcp 常在此目录下索引仓库）。
    engine_id: AOS 引擎 id。
    capability_map: {tool_name: Capability}，未列出的默认 TOOL_USE。
    init_on_start: 构造即 initialize + list_tools；False 则延迟到首次 invoke。
    timeout: 单次读取响应的超时（秒），防止 server 挂死拖垮调用方。
    """

    def __init__(
        self,
        command: list[str],
        engine_id: str,
        args: Optional[list[str]] = None,
        cwd: Optional[str] = None,
        capability_map: Optional[dict[str, Any]] = None,
        init_on_start: bool = True,
        timeout: float = 30.0,
    ) -> None:
        self._cmd = list(command) + list(args or [])
        self._cwd = cwd
        self._engine_id = engine_id
        self._cap_map = capability_map or {}
        self._timeout = float(timeout)
        self._tools: list[dict[str, Any]] = []
        self._healthy = False
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 1
        if init_on_start:
            self._start()

    # ---- 进程管理 ------------------------------------------------
    def _start(self) -> None:
        try:
            self._proc = subprocess.Popen(
                self._cmd,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,  # MCP server 日志走 stderr，不污染协议
                text=True,
                bufsize=1,
                encoding="utf-8",
            )
        except (FileNotFoundError, OSError) as e:
            # 二进制缺失 / 无法启动：优雅失败，绝不谎报 live。
            raise RuntimeError(f"MCP stdio 启动失败 {self._cmd}: {e}") from e
        # 握手 + 列工具；任一阶段失败都向上抛，构造即失败（health()=False）。
        self._initialize()
        self._list_tools()
        self._healthy = True

    # ---- 基础契约 -------------------------------------------------
    @property
    def engine_id(self) -> str:
        return self._engine_id

    def supported_protocols(self) -> list[str]:
        return ["MCP", "stdio"]

    # ---- JSON-RPC 传输（行分隔，stdio） --------------------------
    def _read_line(self) -> str:
        """带超时的单行读取，避免 server 挂死拖垮调用方。"""
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("MCP stdio 进程未就绪")
        bucket: list[Optional[str]] = [None]
        err: list[Optional[BaseException]] = [None]

        def _reader() -> None:
            try:
                bucket[0] = self._proc.stdout.readline()  # type: ignore[union-attr]
            except BaseException as e:  # noqa: BLE001 - 跨线程异常带回主线程
                err[0] = e

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        t.join(self._timeout)
        if t.is_alive():
            # 超时：对话已失同步，标记不健康并放弃本进程，绝不继续读。
            self._healthy = False
            raise RuntimeError(f"MCP stdio 读取超时（>{self._timeout}s），连接已弃用")
        if err[0] is not None:
            raise RuntimeError(f"MCP stdio 读取异常: {err[0]!r}")
        line = bucket[0]
        if line is None or line == "":
            raise RuntimeError("MCP stdio 连接关闭（EOF）")
        return line

    def _rpc(self, method: str, params: Optional[dict] = None,
             notif: bool = False) -> Optional[dict]:
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("MCP stdio 进程未就绪")
        with self._lock:
            rid = None if notif else self._next_id
            if rid is not None:
                self._next_id += 1
            payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if rid is not None:
                payload["id"] = rid
            if params is not None:
                payload["params"] = params
            self._proc.stdin.write(json.dumps(payload) + "\n")
            self._proc.stdin.flush()
            if notif:
                return None
            # 读到 id 匹配的响应为止；跳过 server 可能夹带的 notification（无 id）。
            while True:
                line = self._read_line().strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("id") != rid:
                    # 失同步的 notification 或乱序帧，继续读下一行。
                    if obj.get("id") is None:
                        continue
                    continue
                if "error" in obj:
                    raise RuntimeError(f"MCP stdio 错误 {method}: {obj['error']}")
                return obj.get("result")

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
        return res

    def _list_tools(self) -> list[dict[str, Any]]:
        res = self._rpc("tools/list", {})
        self._tools = (res or {}).get("tools", [])
        return self._tools

    # ---- 能力映射（与 HTTP 适配器同契约） -----------------------
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
        """按「有效能力」精确匹配 tool；无匹配返回 None（诚实失败，绝不落到首 tool）。"""
        cap_str = self._cap_to_str(cap)
        for t in self._tools:
            mapped = self._cap_map.get(t["name"])
            eff = self._cap_to_str(mapped) if mapped is not None else Capability.TOOL_USE.value
            if eff == cap_str:
                return t
        return None

    def health(self) -> bool:
        if not self._healthy or not self._tools:
            return False
        if self._proc is None or self._proc.poll() is not None:
            return False
        return True

    # ---- 执行 -----------------------------------------------------
    def invoke(self, req: InvokeRequest) -> InvokeResult:
        # 14 个工具共用一个 code.understanding 能力时，由 payload["tool"] 指定具体
        # MCP tool；否则用该能力映射到的首个 tool。诚实：无 tool 且无映射则失败，
        # 绝不把任意能力悄悄落到第一个 tool（那是弄虚）。
        tool_name = req.payload.get("tool") or req.payload.get("name")
        if not tool_name:
            tool = self._tool_for_capability(req.capability)
            if tool is None:
                return InvokeResult(
                    ok=False,
                    error=f"mcp-stdio[{self._engine_id}]: 无 tool 映射能力 {req.capability.value}",
                )
            tool_name = tool["name"]
        arguments = req.payload.get("arguments", req.payload.get("params", {}))
        try:
            res = self._rpc("tools/call", {"name": tool_name, "arguments": arguments})
        except Exception as e:  # noqa: BLE001 - 子进程故障隔离
            return InvokeResult(
                ok=False,
                error=f"mcp-stdio[{self._engine_id}] tools/call {tool_name} 失败: {e!r}",
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
        return InvokeResult(ok=True, data={"text": text, "raw": res, "tool": tool_name})

    def shutdown(self) -> None:
        """终止子进程，释放管道。"""
        if self._proc is None:
            return
        try:
            self._rpc("shutdown", notif=False)
        except Exception:  # noqa: BLE001
            pass
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                self._proc.kill()
            except Exception:  # noqa: BLE001
                pass
        self._proc = None
        self._healthy = False
