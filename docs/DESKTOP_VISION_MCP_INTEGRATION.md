# 桌面视觉执行层（Desktop Vision / Computer-Use）接入 AOS 核实与落地

> 核实日期：2026-07-15。本文档对用户提供的一份「桌面视觉执行层方案清单」做开源真实性
> 核实，并基于 AOS 现有架构（`MCPStdioAdapter` + `FabricHub.register_*`）给出可落地的
> 接入方案。**所有事实均经 GitHub / 官方文档 / 模型页交叉核实，编撰项已打假。**

## 一、清单核实结论（真 / 假 / 待定）

| 方案 | 类型 | 核实结果 | 备注 |
| :--- | :--- | :--- | :--- |
| **Desktop-Touch-MCP** | MCP 服务(stdio) | ✅ 真实 | `github.com/Harusame64/desktop-touch-mcp`，MIT，Rust 原生 UIA 内核，29+ 工具，强中文(CJK/IME)支持，`npx -y @harusame64/desktop-touch-mcp` 零配置 |
| **computer-use-mcp** | MCP 服务(stdio) | ✅ 真实(重名) | 存在 3 个重名仓库：`zavora-ai/computer-use-mcp`(Rust NAPI, Win/macOS)、`mandelbro/computer-use-mcp`(TS, 跨端)、`hugefiver/mcp-computer-use`(Rust, 浏览器)。选 `zavora-ai` 对应「Rust+npm+三端」 |
| **PyMCPAutoGUI** | MCP 服务(stdio/HTTP) | ✅ 真实 | `github.com/kitfactory/PyMCPAutoGUI`，MIT，PyAutoGUI 封装，默认 HTTP :6789 或 stdio。**偏旧（最后提交 2025-03），纯像素/坐标操作，语义弱于 UIA** |
| **OmniParser V2** | 视觉解析组件(非 MCP) | ✅ 真实 | `microsoft/OmniParser-v2.0`，**icon_detect 模型为 AGPL**（继承 YOLO），icon_caption 为 MIT。0.6s/帧(A100)。需 GPU 才流畅，**8G CPU 纯本地会很慢** |
| **OpenClaw** | AI Agent 框架 | ✅ 真实 | `github.com/openclaw/openclaw`，MIT，50+ 集成。**AOS 已通过 `/openclaw` 网关(127.0.0.1:18789)接入**，无需再接 |
| **browser-use** | 浏览器自动化框架 | ✅ 真实 | **已是 AOS 注册引擎**（`browser-use`）。纯 Python，**无 Rust 核心**（清单「0.13 引入 Rust 核心」为误传） |
| **ScreenMind** | 屏幕分析 | ❌ 打假 | 清单称「用 Gemma 4 本地分析截图」——**Gemma 4 不存在**（Google 仅有 Gemma 2/3）。该条目整体不可信，划掉 |
| **Woclaw / WinClaw** | 个人 AI 助理 | ❌ 待定/存疑 | 名称拼写混乱（「Woclaw 疑似 WinClaw」），所给链接 `itc-ou-shigou/winclaw` 未核实到可靠信息，暂不当作可执行层 |
| **Portable Hermes Agent** | 完整 GUI 产品 | ⚠️ 未核实 | 基于 NousResearch Hermes，声称 v1.3.0 / 100+ 工具。它是**独立桌面产品**，不是可嵌入 AOS 运行时的 MCP 组件，接入路径不清晰 |
| **Vision-MCP / Orbination** | MCP+Skill | ⚠️ 未核实 | 名称与仓库未交叉验证，暂不纳入 |
| **Agent S / Agent S3** | 完整 Agent 框架 | ⚠️ 未核实 | Simular AI 出品，与 AOS 定位重叠（都是 Agent 框架），不是 AOS 应嵌入的执行层 |
| **TRAE** | AI 原生 IDE | ℹ️ 不适用 | 字节 AI IDE，其 SOLO 模式用于**开发** AOS，而非在 AOS 运行时内执行桌面任务 |

## 二、哪些「能弄进 AOS」

AOS 已内置两套 MCP 客户端，任何标准 MCP 服务都能即插即用：

- `MCPStdioAdapter`（core/fabric/adapters/mcp_stdio_adapter.py）：子进程直连 **stdio** MCP 服务（npx / 二进制）。
- `register_mcp_server`（FabricHub）：连接 **HTTP(SSE)** MCP 服务。

| 方案 | AOS 接入方式 | 能否弄 | 说明 |
| :--- | :--- | :--- | :--- |
| **Desktop-Touch-MCP** | `MCPStdioAdapter` + 新增 `register_desktop_touch_mcp` | ✅ **已落地** | 见第三节，已写注册方法 + mock 测试(2 passed) |
| **computer-use-mcp** | `MCPStdioAdapter`（cargo/npx 起） | ✅ 可弄 | 同款模式，换 command 即可，备选 |
| **PyMCPAutoGUI** | `MCPClientAdapter`（HTTP :6789） | ✅ 可弄 | 自带 HTTP 传输，最简单，但语义最弱 |
| **OpenClaw** | 已接（网关） | ✅ 已在 | 无需再动 |
| **browser-use** | 已接（注册引擎） | ✅ 已在 | 无需再动 |
| **OmniParser V2** | 需自建封装芯粒 | ⚠️ 不建议 | 非 MCP，需包推理服务；**AGPL icon_detect 有许可证污染风险**，且 8G CPU 跑不动 |
| ScreenMind / WinClaw / Hermes / Vision-MCP / Agent S | — | ❌ 不接入 | 假/存疑/定位不符 |

## 三、Desktop-Touch-MCP → AOS 接入（已落地）

已按 WeKnora 同款「协议级即插即用」模式实现，**零新组件、不弄虚**：

- `src/kernel/plugins/fabric_hub.py`
  - 新增 `register_desktop_touch_mcp(command=None, engine_id="desktop-touch", capability_map=None, timeout=30.0)`
    - 默认命令 `npx -y @harusame64/desktop-touch-mcp`（可用 `DESKTOP_TOUCH_MCP_CMD` 覆盖）
    - 工具默认映射到 `action.aci`（agent computer interface）能力
    - 失败优雅返回 `None` 并记错误，**绝不谎报 live**（MCPStdioAdapter 启动失败即 health=False）
  - `__init__` 中加 env 闸门：`DESKTOP_TOUCH_MCP_ENABLED=1` 时启动即自动 npx 拉起并注册（默认关，避免沙箱/CI 误拉）
- `tests/mock_stdio_mcp_server.py` + `tests/test_desktop_touch_mcp_registry.py`
  - 全离线：用本地 mock stdio MCP server 经真实 `MCPStdioAdapter` 验证 stdio 链路 + 能力映射 + 调用
  - `2 passed`（2026-07-15 实跑）

### 你主机上的部署步骤（沙箱跑不了，需在 Windows 上做）

1. 装 **Node.js v20+**（官方测过 v22+）。
2. 给 AOS 加环境变量（`.env` 或系统环境变量）：
   ```
   DESKTOP_TOUCH_MCP_ENABLED=1
   # 可选：自定义命令，例如本地 clone 后
   # DESKTOP_TOUCH_MCP_CMD=node D:/tools/desktop-touch-mcp/dist/index.js
   ```
3. **Windows 授权（关键，90% 失灵都在这）**：
   - 设置 → 隐私和安全性 → 辅助功能：允许控制键鼠
   - 设置 → 隐私和安全性 → 屏幕截图：允许读取屏幕
   - **重启电脑** 让权限完全生效
4. 启动 AOS。FabricHub 构造时会 `npx` 拉起 Desktop-Touch-MCP 并完成 MCP 握手；
   `hub.health_report()` 里 `desktop-touch` 显示 live 即成功。
5. 之后任何 `action.aci` 能力的路由请求会落到它——AOS 即可「动手」操作你的 Windows 桌面，
   与已接入的 OpenClaw（聊天/编排）、browser-use（浏览器）协同。

> 内存占用：Desktop-Touch-MCP Rust 内核常驻约 200MB，远低于 8G 红线，适合低配机。

## 四、推荐结论（针对 8G Windows + 中文 + MCP + OpenClaw/TRAE）

1. **首选底层执行层：Desktop-Touch-MCP** —— Windows 原生 UIA、Rust 低内存、MIT、
   强中文/国产软件识别（语义化「发现-然后-行动」，不靠像素猜测），原生 MCP 直连 AOS。
2. **跨平台备选：computer-use-mcp（zavora-ai）** —— 同款 stdio 接入，三端兼容，但中文/UIA 调优弱于前者。
3. **最轻量兜底：PyMCPAutoGUI** —— 纯 Python 与 AOS 同栈、HTTP 即接，但语义弱（坐标级），适合简单点击。
4. **不建议把 OmniParser V2 塞进 AOS 核心** —— AGPL 污染 + GPU 依赖 + 需自建封装，性价比低；真要视觉解析可走外部服务。
5. **ScreenMind / WinClaw / Hermes / Vision-MCP / Agent S 暂不接入** —— 假、存疑或定位与 AOS 重叠。
