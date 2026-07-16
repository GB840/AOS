# UI-TARS Desktop 部署教程（Windows · 8G 内存 · 纯 CPU 低配）

> 适用场景：你的电脑是 Windows、8G 内存、无独显（纯 CPU）。目标是在本机跑通 UI-TARS Desktop 桌面 GUI 智能体。
>
> ⚠️ **核实与修正提醒（2026-07-15 联网核实）**：原始教程有若干硬错误，本文已按官方事实修正。重点三处：
> 1. 没有"稳定版 v0.3.0"，官方 Release 全是 `v0.3.0-beta.x`，下最新版即可。
> 2. 软件里**没有"Local GGUF"文件直选 provider**；必须用推理服务把 GGUF 起成 OpenAI 兼容端点后填写。
> 3. GGUF 量化版被官方"降级"（性能不保证），8G CPU 能跑但效果打折，建议把期望值放低。

---

## 〇、前置说明

- **仓库**：`bytedance/UI-TARS-desktop`，字节开源的桌面 GUI 智能体框架，**Apache-2.0**（可免费商用）。
- **安装顺序固定**：① 下载安装框架程序 → ② 下载 2B 量化 GGUF 模型 → ③ 用推理服务把模型起成端点 → ④ 软件内绑定端点。
- **硬件限制**：8G 内存**只能**跑 `UI-TARS-2B-SFT-Q4_K_M.gguf`（约 1.1~1.3G）。7B 及以上会爆内存闪退。
- **核心事实**：UI-TARS-desktop 本身只是"操作器 + 调度器"，真正做决策的是背后的 VLM（视觉语言模型）。软件设置里填的是 **VLM Provider + Base URL（OpenAI 兼容端点）+ Model Name**，不能直接吃 GGUF 文件路径。

---

## 一、第一步：下载并安装 UI-TARS Desktop 框架（Windows）

### 1. 官方下载地址
GitHub Releases（取最新版，无需纠结具体版本号）：
```
https://github.com/bytedance/UI-TARS-desktop/releases
```

### 2. 下载对应安装包
页面拉到最下方 **Assets** 区域，找 Windows 安装包：
```
UI-TARS-desktop-Setup-x.x.x.exe   ← 选 Releases 页最新的那一个（形如 0.3.0-beta.x）
```
> 注：不要去搜"v0.3.0 stable"，官方没有稳定版，全是 beta。

### 3. 安装步骤
1. 双击 exe，全部默认下一步；安装路径建议选 **D 盘**（减少 C 盘占用）。
2. 安装完成后**先别急着打开**，先开系统权限（不开无法操控鼠标/截图）。

### 4. Windows 必开 2 个核心权限（关键！多数失灵都是这里没开）
1. **设置 → 隐私和安全性 → 辅助功能**
   - 找到 UI-TARS Desktop，开关全部打开（允许控制键鼠）。
2. **设置 → 隐私和安全性 → 屏幕截图**（部分系统叫"屏幕捕获"）
   - 允许 UI-TARS 读取屏幕画面。
3. **重启电脑**，权限才能完全生效。

### 5. 空载内存占用
只开软件、不加载模型：稳定占用 **600MB ~ 1.2GB**，8G 内存无压力。

---

## 二、第二步：准备适配 8G 内存的本地模型（UI-TARS-2B Q4_K_M GGUF）

### 1. 选对模型与下载源（已核实）
- **正确文件名**：`UI-TARS-2B-SFT-Q4_K_M.gguf`（注意 `SFT` 与 `Q4` 之间是连字符 `-`）。
- **正确下载源**：HuggingFace `bartowski/UI-TARS-2B-SFT-GGUF`（国内可用 hf-mirror 镜像）。
  ```
  https://huggingface.co/bartowski/UI-TARS-2B-SFT-GGUF
  备用镜像：https://hf-mirror.com/bartowski/UI-TARS-2B-SFT-GGUF
  ```
  > ❌ 教程原写的 `modelscope.cn/models/bytedance-research/UI-TARS-2B-gguf` **不存在**。ModelScope 上真实的是 `bytedance-research/UI-TARS-2B-SFT`（原模型，非 GGUF）。GGUF 量化版只在 HuggingFace。
- **文件大小**：约 1.1~1.3G，**不要下 FP16 完整版**（4G+，8G 内存加载直接崩溃）。

### 2. 下载方式（任选其一）
- **网页直接下**：打开上面的 HF 页面 → 找到 `UI-TARS-2B-SFT-Q4_K_M.gguf` → 下载。
- **命令行（hf-mirror，断点续传）**：
  ```bash
  set HF_ENDPOINT=https://hf-mirror.com
  pip install -U "huggingface_hub[cli]"
  huggingface-cli download bartowski/UI-TARS-2B-SFT-GGUF --include "UI-TARS-2B-SFT-Q4_K_M.gguf" --local-dir D:/AI_Model/UI-TARS-2B
  ```

### 3. 存放路径
新建文件夹：
```
D:\AI_Model\UI-TARS-2B\UI-TARS-2B-SFT-Q4_K_M.gguf
```

---

## 三、第三步：把 GGUF 模型起成 OpenAI 兼容端点（关键修正）

> 这是原教程**完全错误**的一步。UI-TARS-desktop 不能直接读 GGUF 文件，必须先起一个推理服务。

### 方案 A（推荐，最轻量）：llama.cpp 服务端（纯 CPU）
1. 下载带 `server`/`llama-server` 的 llama.cpp 发布包（Windows CPU 版，选 `AVX2` 或 `AVX` 对应你 CPU）。
2. 在模型目录起服务（**`-ngl 0` 表示纯 CPU 推理，无独显必须写 0**）：
   ```bash
   llama-server ^
     -m D:/AI_Model/UI-TARS-2B/UI-TARS-2B-SFT-Q4_K_M.gguf ^
     -c 2048 ^
     -t 4 ^
     -ngl 0 ^
     --host 0.0.0.0 --port 8080
   ```
   - `-t 4`：推理线程数 = CPU 物理核心数（i3-7100 是 4 核填 4）。
   - `-c 2048`：上下文长度，拉满会爆内存，8G 建议 2048。
3. 看到日志出现 `HTTP server listening on http://0.0.0.0:8080` 即成功。端点为 `http://localhost:8080/v1`。

### 方案 B（备选）：Ollama
```bash
# 1) 建 Modelfile（同目录下放好 gguf）
# FROM ./UI-TARS-2B-SFT-Q4_K_M.gguf
ollama create ui-tars-2b -f Modelfile
ollama serve   # 默认端点 http://localhost:11434/v1
```

---

## 四、第四步：框架内配置模型（完整部署）

1. 打开 UI-TARS Desktop，右上角齿轮「设置」。
2. 找到 **VLM Settings（VLM 模型配置）**。
3. 按如下填写（这是官方支持的写法，**不是**"Local GGUF 文件直选"）：
   | 配置项 | 填法（8G CPU 本地） |
   |---|---|
   | VLM Provider | `vLLM`（即 OpenAI 兼容端点；也可选 Hugging Face 填同款 Base URL） |
   | VLM Base URL | `http://localhost:8080/v1`（llama.cpp）或 `http://localhost:11434/v1`（Ollama） |
   | VLM API Key | 本地随便填，如 `sk-local`（云端才需真 key） |
   | VLM Model Name | `UI-TARS-2B-SFT-Q4_K_M.gguf`（与第三步服务暴露的模型名一致） |
   | Language | `zh`（中文界面/中文指令更顺） |
4. 点击 **Check Model Availability**（模型可用性检测），显示可用即连通。
5. **CPU 参数优化（8G 低配必调，防卡顿）**：
   - 推理线程：填 CPU 物理核心数（4 核填 4）。
   - 上下文长度：2048（拉满会爆内存）。
   - 关闭「实时屏幕预览渲染」（如有此开关）。
6. 保存，等模型加载完成、无报错即部署成功。

### 整机内存占用测算（8G 电脑）
- Windows 开机：≈ 2.8G
- UI-TARS 框架：≈ 1G
- 2B 量化模型常驻（llama.cpp）：≈ 2.2G
- **合计 ≈ 6G**，剩约 2G 余量，可稳定运行简单自动化任务。

---

## 五、两种备用方案（不想本地跑模型）

### 方案 A：云端 API（零本地内存，最简单）
1. 无需下载任何模型。
2. VLM Provider 选云端：`VolcEngine Ark for Doubao-1.5-UI-TARS` / `Hugging Face` / 自定义 OpenAI 兼容。
3. 填平台 API Key + Base URL，保存即用，推理全在云端，本地只负责截图、模拟键鼠。
- 缺点：需充值额度、依赖网络。

### 方案 B：源码编译（开发者，不推荐新手）
```bash
git clone https://github.com/bytedance/UI-TARS-desktop.git
cd UI-TARS-desktop
npm install -g pnpm
pnpm install
pnpm run dev:desktop
```
需 Node.js 环境，普通用户直接用 exe 安装包即可。

---

## 六、8G 低配机使用避坑规则

1. 跑 UI-TARS 时，关掉浏览器、微信、视频等吃内存程序。
2. 只执行 **3~5 步简单任务**（打开软件、点按钮、输文字），超长多步任务 2B 模型易识别出错。
3. 长时间闲置可在设置里「卸载模型」，只留框架后台挂机释放内存。
4. **仅支持单显示器**，多屏会坐标偏移、点击失效。
5. Windows **屏幕缩放必须 100%**，125%/150% 缩放会导致识别按钮错位。
6. GGUF 是量化版，官方已声明性能不保证——复杂界面识别率低于 7B/云端，预期管理好。

---

## 七、测试验证是否部署成功

在软件聊天框输入指令：
```
打开浏览器，搜索 UI-TARS 教程
```
正常效果：自动点击桌面浏览器图标、跳转搜索页面 → 代表「框架 + 本地模型端点」整条链路打通。

> 若点击不动：先确认第三步的 llama.cpp/Ollama 服务还在跑、Base URL 填对、权限已开且重启过。

---

## 附：原始教程中的错误对照（已修正）
| 原教程说法 | 实际情况 |
|---|---|
| 选稳定版 v0.3.0 | 官方无稳定版，全是 `v0.3.0-beta.x`，下最新即可 |
| 提供商选"Local GGUF 本地量化模型"、直接选 gguf 文件 | 软件无此 provider；须用推理服务起 OpenAI 兼容端点后填 Base URL |
| 模型名 `UI-TARS-2B-SFT.Q4_K_M.gguf` | 正确为 `UI-TARS-2B-SFT-Q4_K_M.gguf`（Q4 前是连字符） |
| ModelScope `bytedance-research/UI-TARS-2B-gguf` | 该页不存在；GGUF 在 HF `bartowski/UI-TARS-2B-SFT-GGUF` |
| （隐含）GGUF 效果等同原模型 | 官方已"降级"GGUF，性能不保证 |
