# AOS × ida-pro-mcp 本机逆向工程芯粒（re.ida）

> 把 [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp)（真实开源，MIT，
> GitHub 546 commits，2026-06 增长最快的安全项目之一）接入 AOS 供给面，落实「万物为我所用」
> 的第 4 条理念。它通过 MCP 协议把**你本机运行的 IDA Pro** 连到 LLM，让 AI 能反编译 /
> 重命名 / 加注释 / 查交叉引用。
>
> 本文是接入与**安全边界**的单一真相（红线、写操作 opt-in、调试类 unsafe 工具的开销与风险）。
> 数据来源：ida-pro-mcp README（GitHub，MIT，2026-06 核实）；工具清单与风险分类见
> `src/core/fabric/adapters/ida_pro_mcp_adapter.py` 的 `_UNSAFE_TOOLS_RISK`，可经
> `IdaProMcpAdapter.explain_unsafe_tools()` 在运行时查询。

## 0. 一句话定位

AOS 的 `re.ida` 芯粒**只连接你自己的 IDA 实例（localhost）**，只做静态/只读逆向分析，
**永久拒绝**调试器类 unsafe 工具。它不判断二进制来源，但你须确保对加载进 IDA 的二进制
有合法分析权。

## 1. 红线（不可越过）

对应理念 5「权限即边界」+ 理念 6/9「诚实可验证」+ 内容策略：

1. **仅连接 localhost 的 ida-pro-mcp server**（你自己机器上的 IDA 实例）。
   非本机 URL 一律诚实拒绝——绝不连别人的 IDA、绝不碰你无权分析的二进制。
   注册时校验 **+** 每次 `invoke` 入口再校验（纵深防御，防运行时 url 漂移）。
2. **只做静态/只读分析**（反编译、列函数、查字符串、给自有 IDB 加注释），
   **永久拒绝**调试器类 unsafe 工具（`dbg_*`）。这些工具由 IDA 侧 `?ext=dbg` 启用
   （非 `--unsafe` 启动标志），需 IDA Pro 调试器许可 + 一个运行中的调试会话，
   开销与风险远高于静态分析——最高危 `dbg_write` 可 corrupt 进程内存、`py_eval` 可凭
   任意 Python 代码损坏 IDB。
3. **你负责确保对加载进 IDA 的二进制有合法分析权**（你自己的程序 / 已授权审计 / 开源软件）。
   本适配器不判断二进制来源，但任何对外/对第三方目标的用途都越界。

## 2. 用户主机接入步骤（沙箱无法跑 IDA，仅你本机执行）

```powershell
# 1) 安装 ida-pro-mcp（Python 3.11+，IDA Pro 8.3+ 推荐 9；IDA Free 不支持调试器）
pip install --upgrade git+https://github.com/mrexodia/ida-pro-mcp

# 2) 安装 IDA 插件
ida-pro-mcp --install

# 3) 启动 IDA Pro 并加载目标二进制（.idb / .i64）
# 4) 启动 MCP server（默认 http://localhost:13337/mcp）
#    若需调试器扩展，连 IDA 侧时追加 ?ext=dbg —— 但 AOS 适配器会永久拒绝 dbg_* 工具

# 5) 告诉 AOS 你的本机 server 地址（仅 localhost 生效）
$env:IDA_PRO_MCP_URL = "http://localhost:13337/mcp"
```

AOS 侧：`FabricHub` 在 `IDA_PRO_MCP_URL` 存在且为 localhost 时自动注册 `re.ida` 芯粒；
非 localhost 直接拒绝注册。传输仅用标准库（`urllib` + JSON-RPC 2.0），无第三方依赖。

支持 20+ AI 客户端（Claude / Cursor / 各类 MCP host），AOS 以适配器形式复用其 MCP 协议原语。

## 3. 工具面与权限分级

| 分级 | 工具示例 | AOS 默认策略 |
|------|----------|--------------|
| 只读（静态分析） | `get_metadata` / `decompile` / `disasm` / `xrefs_to` / `list_funcs` / `imports` / `rename`(需 opt-in) | ✅ 默认放行（写操作需 `read_only=False`） |
| 写操作（改 IDB） | `rename` / `comment` / `set_struct_member_name` / `add_enum` … | ⚠️ 默认只读拦截，显式 `read_only=False` 才放行 |
| 调试类 unsafe（`dbg_*`） | 见下表 | ❌ **永久拒绝**，即便显式 opt-in 也返回 `blocked_reason=unsafe_debug_tool` |
| 任意代码 | `py_eval` | ❌ 永久拒绝（性质同 unsafe，见下表） |

调用示例（只读）：

```python
res = adapter.invoke(InvokeRequest(
    capability=Capability.RE_IDA,
    payload={"tool": "decompile_function", "arguments": {"address": 0x1000}},
))
```

写操作需显式声明：

```python
res = adapter.invoke(InvokeRequest(
    capability=Capability.RE_IDA,
    payload={"tool": "rename", "arguments": {...}, "read_only": False},
))
```

## 4. 调试类 unsafe 工具：开销与风险（为什么永久拒绝）

`dbg_*` 工具由 IDA 侧 `?ext=dbg` 启用，需要 **IDA Pro 调试器许可 + 一个运行中的调试会话**。
下表逐类列出开销与风险（与 `IdaProMcpAdapter.explain_unsafe_tools()` 返回一致）：

| 类别 | 工具 | 开销 | 风险 |
|------|------|------|------|
| 控制（control） | `dbg_start` `dbg_exit` `dbg_continue` `dbg_run_to` `dbg_step_into` `dbg_step_over` | 需启动/附加调试器，占用 IDA 调试会话与系统进程；失败可能遗留僵尸进程 | **高**：错误地址/断点可致被调试进程崩溃或调试状态不一致 |
| 断点（breakpoint） | `dbg_bps` `dbg_add_bp` `dbg_delete_bp` `dbg_toggle_bp` | 依赖调试会话；误配致频繁 SIGTRAP 拖慢目标 | **中**：误删/误加断点错过分析时机 |
| 内存写（memory_write） | `dbg_write` | 需调试会话；直接写入目标进程内存 | **极高**：写错地址/数据可 corrupt 进程内存、改变执行流、造成崩溃 |
| 只读（read_only） | `dbg_regs` `dbg_regs_all` `dbg_gpregs` `dbg_stacktrace` `dbg_read` … | 需调试会话；纯读取 | **低**：只读，依赖会话稳定性 |
| 任意代码（arbitrary_code） | `py_eval` | 在 IDA 进程内执行任意 Python；可调全部 IDA 内部 API | **极高**：可凭任意代码损坏 IDB、篡改反汇编、植入脚本 |

**要点**：
- `dbg_write` 与 `py_eval` 是两类「极高」风险——前者改的是**被调试进程**的内存（可崩溃它），
  后者改的是 **IDA 自身的数据库（IDB）**（可永久损坏你的分析工程）。二者都远超静态分析的安全边界。
- AOS 适配器**不提供任何开关**启用 `dbg_*` 或 `py_eval`：`invoke` 入口在 tool 以 `dbg_` 开头或
  为 `py_eval` 时直接返回拒绝，并附带 `unsafe_risk_summary` 供审计。
- 若你确实需要调试器能力，应在**独立、隔离、已授权**的 IDA 实例里直接用 ida-pro-mcp，
  而非经 AOS 的 `re.ida` 芯粒（AOS 刻意不暴露这条攻击面）。

## 5. 运行时可复核接口

```python
from core.fabric.adapters.ida_pro_mcp_adapter import IdaProMcpAdapter

# 查询红线拒了什么、开销/风险多大（诚实非黑箱）
risk = IdaProMcpAdapter.explain_unsafe_tools()
print(risk["memory_write"]["risk"])  # "极高：写错地址/数据可 corrupt 进程内存…"

# 调用调试工具 → 被拒且附带风险摘要
res = adapter.invoke(InvokeRequest(
    capability=Capability.RE_IDA, payload={"tool": "dbg_write"}))
assert res.ok is False
assert res.data["blocked_reason"] == "unsafe_debug_tool"
assert "?ext=dbg" in res.data["unsafe_risk_summary"]
```

## 6. 测试与合规

- `tests/test_ida_pro_mcp_adapter.py`：localhost 红线、能力映射、只读默认、写操作 opt-in、
  `dbg_*` 永久拒绝、`explain_unsafe_tools()` 风险表、`invoke` 拒绝时风险摘要。
- 全部仅 localhost、纯只读/结构化响应，无真实 IDA 依赖（transport 可注入伪造 server）。
- 与 `AGENTS.md` §5「权限即边界」、§1.10「原因与影响驱动」系统本能对齐。
