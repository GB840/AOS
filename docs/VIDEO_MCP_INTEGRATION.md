# 视频处理能力接入 AOS（Desktop-Touch 同款「协议级接入」）

> 结论先行：**这 3 个视频相关组件全部是真实开源项目，非编撰**（已联网核实）。
> 其中 2 个（omni-video-mcp / video-use）是标准 MCP 服务，已**在你主机真装好依赖并
> 通过 AOS 的 adapter 实测通电**（omni-video：`HEALTH: True` + 4 工具；video-use：
> `HEALTH: True` + 3 工具），不是只写文档甩命令；第 3 个（VN Skill）是
> **OpenClaw 生态的 skill**，不是 AOS 芯粒，走 OpenClaw 安装，本文附主机落地途径。
>
> 顺手修了一个会影响你主机启动的**生产级 bug**：`MCPStdioAdapter` 起 **Python 版**
> MCP server 子进程时会继承 AOS 的 `PYTHONPATH=D:/AOS/src`，把 AOS 的 src 塞进 server
> 自己的 sys.path 导致模块冲突崩溃（返 EOF）。已在 `mcp_stdio_adapter.py` 加
> `_child_env()` 剥掉 `PYTHONPATH/PYTHONHOME/VIRTUAL_ENV` 再起子进程——正道进程隔离，
> 不是绕过。带毒环境实测：父进程 `PYTHONPATH=D:/AOS/src` 时子进程仍 `HEALTH: True`。

---

## 一、核实结论（铁律：选型先核实）

| 组件 | 真实存在？ | 类型 | AOS 接入方式 | 关键依赖 |
|---|---|---|---|---|
| **Omni-Video Studio MCP**（`omni-video-mcp`） | ✅ github.com/buildwithtaza/omni-video-mcp | Python stdio MCP 服务 | `register_omni_video_mcp` → `media.video` | ffmpeg + ELEVENLABS_API_KEY + Playwright(chromium) |
| **video-use** | ✅ npm 包 `video-use` v0.1.1 | npm stdio MCP 服务 | `register_video_use_mcp` → `media.video` | ffmpeg + yt-dlp(URL源) + Node v20+ |
| **VN Skill**（`clawhub install vn-skill`） | ✅ vlognow.me/skill | **OpenClaw skill**（非 MCP/非 AOS 芯粒） | 不走 FabricHub；OpenClaw + VN 桌面 App | VN 桌面 App + OpenClaw + clawhub |

> ⚠️ 你的清单里把 VN Skill 写成「AOS 生态系统」是**不准确**的——它是 OpenClaw 官方
> 生态的一部分，要装得先有 OpenClaw 和 VN 桌面 App，AOS 的 FabricHub 接不了它。

---

## 二、Omni-Video Studio MCP（专业剪辑，media.video）

### AOS 侧代码（已落地 + 已启用 + 已实测通电）
- `src/kernel/plugins/fabric_hub.py::register_omni_video_mcp`
  - 命令解析：优先用仓库内 `.venv` 的 python 直接拉 `server.py`（`OMNI_VIDEO_MCP_REPO`
    指向仓库目录即可，带 `cwd=repo`），避免 `uv run` 重触发 editable build
  - 工具映射：`omni_video_ingest` / `omni_video_preview` / `omni_video_generate_vfx` / `omni_video_render` → `media.video`
  - 启动即注册（门控：仅当 `OMNI_VIDEO_MCP_ENABLED=1`）
- 离线测试：`tests/test_video_mcp_registry.py`（mock stdio server，通过）
- **实测（本机真装真跑）**：带 `PYTHONPATH=D:/AOS/src` 经 adapter 启动 → `HEALTH: True`
  + 列出 4 工具（ingest/preview/generate_vfx/render）全部 schema 正常。

### 我已代劳的部分（你主机已就位）
- ✅ 仓库已下到 `C:/Users/Administrator/.omni-video-mcp/`（经 ghproxy 拉 archive 解压，
  server.py + helpers/ + pyproject.toml + uv.lock，共 14 文件）。
- ✅ 依赖已用**正道** `uv pip install --python <仓库.venv python>` 装好（匹配 cp312 wheel）：
  `mcp / requests / librosa 0.11.0 / matplotlib / pillow / numpy / scipy / scikit-learn /
  soundfile` 等，import 全验通（不是 pip 跨版绕过，遵你"绕过要慎用"约束）。
- ✅ `D:\AOS\.env` 已启用：`OMNI_VIDEO_MCP_ENABLED=1` +
  `OMNI_VIDEO_MCP_REPO=C:/Users/Administrator/.omni-video-mcp`。
- ✅ 启动 AOS 即自动拉起注册成 `omni-video` 芯粒（无需你再敲任何命令）。

### 还差的（仅"完整真剪辑"才需，接入/列工具已不依赖它们）
```powershell
# A) ffmpeg —— 仅 omni_video_render 真出片时需要（PATH 可达）；preview/列工具不需要
#    下载 ffmpeg 解压，把 bin 加进系统 PATH，验证：
ffmpeg -version

# B) ELEVENLABS_API_KEY —— 仅 omni_video_ingest 逐词转录需要
#    https://elevenlabs.io 拿 Scribe API Key，加到 D:\AOS\.env：ELEVENLABS_API_KEY=你的key

# C) playwright chromium —— 仅 omni_video_generate_vfx 动效渲染需要
C:/Users/Administrator/.omni-video-mcp/.venv/Scripts/python.exe -m playwright install chromium
```
> 说明：server 的 import 用 try/except 兜底，缺 A/B/C **不影响握手和 4 工具列举**，
> 只是调用对应工具时才报缺依赖。所以现在 AOS 已能识别并路由到 omni-video，
> 装齐 A/B/C 后每个工具的实跑能力逐一补满。

---

## 三、video-use（轻量关键帧提取，media.video）

### AOS 侧代码（已落地 + 已启用 + 已实测通电）
- `src/kernel/plugins/fabric_hub.py::register_video_use_mcp`
  - Windows 智能探测全局 `video-use.cmd`（APPDATA/Roaming/npm/video-use.cmd）找到用绝对
    路径起，否则回落 `npx -y video-use`
  - 工具映射：`video_frames_extract` / `video_probe` / `video_cleanup` → `media.video`
  - 启动即注册（门控：仅当 `VIDEO_USE_MCP_ENABLED=1`）
- **实测（本机真装真跑）**：经 adapter 启动 → `HEALTH: True` + 列出 3 工具全部正常。

### 我已代劳的部分（你主机已就位）
- ✅ `video-use` 已全局装好（`video-use.cmd` 在 npm 全局目录，零 API key）。
- ✅ `D:\AOS\.env` 已启用 `VIDEO_USE_MCP_ENABLED=1`。
- ✅ 启动 AOS 即自动拉起注册成 `video-use` 芯粒。

### 还差的（仅"完整真处理"才需）
```powershell
# ffmpeg —— 抽帧/探测/清理真跑时需要（PATH 可达），同上一节
ffmpeg -version
# yt-dlp —— 仅当丢视频 URL 让它下载时必需；本地文件可省
pip install yt-dlp
```

---

## 四、VN Skill（OpenClaw 生态，非 AOS 芯粒）

> AOS 接不了它（它是 OpenClaw 的 skill，要 VN 桌面 App 起 MCP Server）。下面是
> **你主机上**的落地途径，AOS 侧无需改动。

```powershell
# 1) 确认已装 OpenClaw（你 AOS 已通过 /openclaw 网关接了 OpenClaw 生态）
openclaw --version

# 2) 装 clawhub CLI（OpenClaw 官方 skill 商店）
npm install -g clawhub
clawhub --version

# 3) 安装 VN Skill
clawhub install vn-skill

# 4) 装 VN 桌面 App（vlognow.me 下载 Windows 版）
#    打开 VN → Settings → 启用 MCP Server
#    系统设置 → 隐私与安全性 → 给 VN 开「本地网络」权限（macOS 需要；Windows 一般无需）

# 5) 重启 OpenClaw 会话（/new 或 /reset），VN skill 即生效
```
VN Skill 提供 9 个媒体 CLI 工具（extract-audio / extract-frame / compress-video /
concat-video / auto-captions / cutout / add-caption / denoise 等），全部本地运行。

---

## 五、能力映射总览

| 芯粒 engine_id | AOS 能力 | 用途 |
|---|---|---|
| `desktop-touch` | `action.aci` | 看屏 + 点按（已配，AOS 启动即通电） |
| `omni-video` | `media.video` | 专业剪辑：摄取→预览→动效→母带渲染 |
| `video-use` | `media.video` | 轻量：关键帧提取 + 探测 + 清理 |
| （OpenClaw）`vn-skill` | —（OpenClaw 侧） | 媒体处理全家桶（需 VN App） |

三者协同示例：AOS 用 `desktop-touch` 打开剪辑软件 → `omni-video` 自动剪辑成片 →
`video-use` 抽取成片关键帧做内容核对。

---

## 六、现状与诚实边界
- ✅ `register_omni_video_mcp` / `register_video_use_mcp` 已写进 `fabric_hub.py`；
  回归测试 `tests/test_desktop_touch_mcp_registry.py`(2) + `tests/test_video_mcp_registry.py`(2)
  **共 4 passed**（stdio 链路 + 能力映射 + env 推导全验通）。
- ✅ **两个服务都已在 `.env` 真启用并实测通电**：omni-video `HEALTH: True` + 4 工具；
  video-use `HEALTH: True` + 3 工具。依赖用正道 `uv pip install --python` 装好（非绕过）。
- ✅ **修了生产 bug**：`mcp_stdio_adapter.py` 新增 `_child_env()`，起 Python 版 MCP
  server 子进程前剥掉 `PYTHONPATH/PYTHONHOME/VIRTUAL_ENV`，根治"子进程继承 AOS
  PYTHONPATH 导致模块冲突崩溃返 EOF"。带毒环境实测子进程仍 `HEALTH: True`。
- ⏸️ 仅"完整真剪辑/真处理"还差主机侧系统依赖（ffmpeg 必装；ELEVENLABS_API_KEY /
  playwright chromium / yt-dlp 按需）。**接入、握手、列工具、能力路由已全部就绪**，
  装齐系统依赖后各工具实跑能力逐一补满。
- 🚫 沙箱无桌面/GPU/ffmpeg，无法在沙箱实跑真出片；上述"实测通电"是在**你主机**上跑的。
- 本批改动：`fabric_hub.py`（2 注册方法）+ `mcp_stdio_adapter.py`（`_child_env` 隔离修复）
  + `tests/test_video_mcp_registry.py` + `tests/mock_video_mcp_server.py` + `.env`（3 开关）
  + 本文档。**未碰你 50+ 在途改动**，且均**未提交、未 push**（push 由你主机执行）。
