# Desktop-Touch-MCP 主机落地途径（Windows · 8G 低配 · 直接照敲）

> ## ✅ 2026-07-15 已由 AI 直接代劳完成（你不用再敲下面大部分命令）
> - 探明：你主机 `~\.desktop-touch-mcp\releases\v1.12.1\` **早已完整解压好**（npx 之前的 `fetch failed` 是瞬时重试失败，文件其实落地了）。
> - 已把 `D:\AOS\.env` 配好：`DESKTOP_TOUCH_MCP_ENABLED=1` + `DESKTOP_TOUCH_MCP_CMD=node C:/Users/Administrator/.desktop-touch-mcp/releases/v1.12.1/dist/index.js`（**绕过 npx / GitHub，直接用本地二进制**）。
> - 已从沙箱实跑验证：拉起本地二进制 → `HEALTH: True` → **32 个工具全部暴露**（screenshot/mouse_click/keyboard/click_element/workspace_snapshot…），原生引擎加载正常。
> - **你只剩一件事**：在你主机上正常启动 AOS（见文末「阶段 5：启动即通电」）。启动后 `desktop-touch` 芯粒自动注册，和 `openclaw`/`browser-use` 协同动手。
> - 下面阶段 0~4 保留作排障参考；正常情况你跳到阶段 5 即可。

---

## 阶段 5（你唯一要做的）：启动 AOS 即通电

在 **PowerShell** 里正常启动 AOS（你平时怎么起就怎么起，例如）：

```powershell
cd D:\AOS
$env:PYTHONPATH = "D:/AOS/src"
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m src.api.main
# 或你惯用的启动方式
```

启动日志里应出现 `desktop-touch` 注册成功（或 FabricHub 注册表含 `desktop-touch` 引擎）。
随后在 AOS 对话里下指令如「打开浏览器，搜索 UI-TARS 教程」，AOS 会路由到 `desktop-touch` 芯粒，
由它在本机真实操控鼠标/键盘/读屏完成。

> 急停：把鼠标移到屏幕左上角 (0,0) 10px 内，服务即终止（Desktop-Touch-MCP 内置安全急停）。

---

## 阶段 0：确认主机环境（3 条命令，先排除环境问题）

在 **PowerShell**（管理员与否都行）里逐条跑：

```powershell
# 1) Windows 版本（确认是 10/11 64 位）
winver

# 2) Node.js 版本（必须 ≥ v20，官方测过 v22+）
node -v
#    期望输出形如：v22.22.2 或 v24.x.x
#    若报错"node 不是内部或外部命令"或版本 < v20 → 去 https://nodejs.org 装 LTS（v20+/v22）

# 3) PowerShell 版本（Windows 10/11 自带 5.1，够用）
$PSVersionTable.PSVersion.Major
#    期望输出：5 或更高
```

> 你主机上已知有 `C:\Program Files\nodejs\node.exe`（v24.16.0），所以 `node -v` 多半直接过。

**补装一项依赖（一次性）**：desktop-touch 的 nut-js 原生绑定需要 Visual C++ Redistributable。
- 下载：https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist
- 选 **X64** 版本，双击安装，下一步到底。

---

## 阶段 1：先脱离 AOS，单独验证 `npx` 能拉起服务（最关键，先排除包本身问题）

```powershell
# 直接前台跑，看它能不能下载→校验→握手
npx -y @harusame64/desktop-touch-mcp
```

**正常预期（首次运行）**：
1. npx 解析包版本；
2. 从 GitHub Releases 下载 `desktop-touch-mcp-windows.zip`，**校验 SHA256**；
3. 解压到 `%USERPROFILE%\.desktop-touch-mcp`；
4. 启动 Rust 原生引擎，进程**停在 stdin 等待 JSON-RPC**（不退出、不报错，光标在那闪）。

→ 此时**它就是活的**，按 `Ctrl+C` 退出即可。阶段 1 通过。

**失败排查**：
- `npm error` / 找不到包 → Node 没装好或版本太低，回阶段 0。
- 卡在下载 / `GitHub API rate limit` → 国内或共享网络匿名限速（60 次/小时/IP）。解决：
  ```powershell
  # 设一个 GitHub token（https://github.com/settings/tokens 建个只读 classic token 即可）
  $env:GITHUB_TOKEN = "ghp_你的token"
  npx -y @harusame64/desktop-touch-mcp
  ```
- **`[desktop-touch-mcp] Downloading ...zip` 之后报 `fetch failed`** →
  **这是 GitHub Releases 的二进制 zip CDN 被墙/不通**（不是包问题：npm 源能下包、git 能推，就卡在那个 `desktop-touch-mcp-windows.zip` 下载）。按下面「排障 A：手动走镜像下 zip」解决。
- 被杀软拦截 → 把 `%USERPROFILE%\.desktop-touch-mcp` 整个目录加 Defender/杀软白名单。

### 排障 A：`fetch failed` 时手动走 GitHub 镜像下 zip（最常用）

npm 启动器只是个**薄壳**，真干活的是它从 GitHub Releases 拉的 `desktop-touch-mcp-windows.zip`（版本号随包走，当前是 `v1.12.1`）。这个 zip 下不下来就啥都干不了。镜像能下，就手动下好塞进它的缓存目录，启动器会校验 SHA256 后直接复用、跳过失败的 fetch。

```powershell
# 0) 先确认确实是网络层拉不到（可选，验证用）
curl.exe -I https://github.com/Harusame64/desktop-touch-mcp/releases/download/v1.12.1/desktop-touch-mcp-windows.zip
#    若 curl 也失败/超时 → 坐实 GitHub 发布 CDN 不通，走下面镜像。

# 1) 建缓存目录
$home = "$env:USERPROFILE\.desktop-touch-mcp"
New-Item -ItemType Directory -Force -Path $home | Out-Null

# 2) 用 GitHub 镜像把 zip 拉下来（任选一个能通的镜像；第三方镜像，自行判断可用性）
$ver = "v1.12.1"
$asset = "desktop-touch-mcp-windows.zip"
$mirror = "https://ghproxy.net/https://github.com/Harusame64/desktop-touch-mcp/releases/download/$ver/$asset"
# 备选镜像（上面不通就换）：
#   $mirror = "https://ghfast.top/https://github.com/Harusame64/desktop-touch-mcp/releases/download/$ver/$asset"
#   $mirror = "https://mirror.ghproxy.com/https://github.com/Harusame64/desktop-touch-mcp/releases/download/$ver/$asset"
Invoke-WebRequest -Uri $mirror -OutFile "$home\$asset"

# 3) 验证文件真的下到了（应该 ~几 MB 到几十 MB，不是 0 字节）
Get-Item "$home\$asset" | Select-Object Length,Name

# 4) 重新跑启动器（版本钉死成同一个，避免它又去拉别的版本）
npx -y @harusame64/desktop-touch-mcp@1.12.1
```

> 若启动器仍报 fetch/校验失败：说明它除了 zip 还要从 GitHub 取 SHA256 摘要（镜像只代理了 zip，摘要仍走不通）。此时换**有个人代理**的环境，或手动把 zip 解压到 `$home` 后直接本地起（见排障 B）。

### 排障 B：彻底离线——本地解压 + 直接起 `node dist/index.js`
若镜像也只能拿到 zip、启动器校验仍要联网，就自己解压、绕开启动器：
```powershell
$home = "$env:USERPROFILE\.desktop-touch-mcp"
Expand-Archive -Path "$home\desktop-touch-mcp-windows.zip" -DestinationPath $home -Force
# 找到解压后的入口（一般是 dist/index.js 或 index.js），用绝对路径注册到 AOS：
#   编辑 D:\AOS\.env 加一行：
#   DESKTOP_TOUCH_MCP_CMD=node C:/Users/Administrator/.desktop-touch-mcp/dist/index.js
#   然后正常启动 AOS（阶段 3）即可，不再走 npx。
```

---

## 阶段 2：Windows 权限与急停（防拦截 + 安全）

- **Windows 下 UIA 一般不需要 macOS 那种"辅助功能"开关**，desktop-touch 用原生 Rust UIA 引擎，通常直接可用。
- 唯一要防的是**杀软误杀**：把解压目录加入白名单（阶段 1 已提）。
- **急停保护**：鼠标移到屏幕**左上角 (0,0) 10px 内**，服务会立即终止（Failsafe），跑自动化时手边留个这种退路。

---

## 阶段 3：在 AOS 里"通电"

AOS 侧代码已就绪：启动时会读 `DESKTOP_TOUCH_MCP_ENABLED`，为 `1` 才自动 `npx` 拉起并注册成 `desktop-touch` 芯粒。

**1) 编辑 AOS 的环境文件** `D:\AOS\.env`，加一行（用记事本或任意编辑器）：

```ini
# 启用桌面视觉执行芯粒（Desktop-Touch-MCP）
DESKTOP_TOUCH_MCP_ENABLED=1
```

> 可选：想用自己 clone 的本地版（而不是 npx 拉），加：
> ```ini
> DESKTOP_TOUCH_MCP_CMD=node D:/path/to/desktop-touch-mcp/dist/index.js
> ```
> 默认就是 `npx -y @harusame64/desktop-touch-mcp`，一般不用改。

**2) 正常启动 AOS**（用你平时的方式，例如）：

```powershell
cd D:\AOS
$env:PYTHONPATH = "D:/AOS/src"
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -m src.api
```

AOS 启动日志里应能看到 `register_desktop_touch_mcp` 相关行；若 npx 拉起失败，会在 FabricHub 的 `_errors["desktop-touch:desktop-touch"]` 记原因，**绝不谎报 live**。

---

## 阶段 4：验证"通电"真的成功（两条任选）

### 方式 A：独立握手验证（最硬，直接证明 stdio 链路通）
在 PowerShell 跑（会真实拉起 npx 并握手，首次约几十秒，别急着 Ctrl+C）：

```powershell
cd D:\AOS
C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe -c "import sys; sys.path.insert(0,'D:/AOS/src'); from core.fabric.adapters.mcp_stdio_adapter import MCPStdioAdapter; a=MCPStdioAdapter(command=['npx','-y','@harusame64/desktop-touch-mcp'], engine_id='desktop-touch', timeout=120); print('HEALTH:', a.health()); print('TOOL_COUNT:', len(a._tools)); print('SAMPLE_TOOLS:', [t.get('name') for t in a._tools[:5]])"
```

**预期输出**：
```
HEALTH: True
TOOL_COUNT: 29
SAMPLE_TOOLS: ['desktop_discover', 'desktop_act', 'desktop_state', 'screenshot', 'mouse_click']
```
→ `HEALTH: True` + 工具数 > 0 = 通电成功。

### 方式 B：看 AOS 注册表
AOS 起来后，查 FabricHub 注册表里 `action.aci` 能力下有没有 `desktop-touch` 供给方（具体查询命令取决于你 AOS 的调试入口；最简是方式 A）。

---

## 阶段 5：和 OpenClaw / browser-use 协同

通电后，`desktop-touch` 是 `action.aci`（动手/操控机器）能力的供给方之一。编排时：
- `openclaw` 负责云端/外部集成与调度；
- `browser-use` 负责浏览器内操作；
- `desktop-touch` 负责**操作系统级桌面**（点 EXE、填表单、读屏、键鼠）；
- 三者经 FabricHub 单一内核统一路由，按能力调用，互不重写脑子。

示例意图："打开本机微信、给某人发消息" → 路由到 `desktop-touch`；"查网页资料" → 路由到 `browser-use`。

---

## 附：停用 / 卸载

- **临时停用**：把 `D:\AOS\.env` 里的 `DESKTOP_TOUCH_MCP_ENABLED=1` 改成 `0` 或删掉，重启 AOS 即不再拉起。
- **彻底卸载**：`rmdir /s %USERPROFILE%\.desktop-touch-mcp` 删掉解压目录即可；AOS 侧只是注册入口，不影响其他芯粒。

---

### 一句话总结
装好 Node v20+ 和 VC Redist → `npx -y @harusame64/desktop-touch-mcp` 单独验证能跑 → `D:\AOS\.env` 加 `DESKTOP_TOUCH_MCP_ENABLED=1` → 启动 AOS → 用阶段 4 的 Python 片段确认 `HEALTH: True`。全程你在主机上敲，沙箱只负责把"接入口子"焊死并测通。
