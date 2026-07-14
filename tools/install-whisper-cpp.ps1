# =========================================================================
# AOS 全离线语音：安装 whisper.cpp（本地 STT，零云端依赖）
# 在 D:\AOS 目录下用 PowerShell 运行本脚本：
#   cd D:\AOS; powershell -ExecutionPolicy Bypass -File tools\install-whisper-cpp.ps1
#
# 前置依赖（脚本会检查，缺了会明确报错退出）：
#   1) cmake          —— https://cmake.org/download/  （装完把 bin 加进 PATH）
#   2) C++ 编译器      —— Visual Studio 2022（勾「使用 C++ 的桌面开发」）或 MinGW-w64
#   3) git            —— 一般已有
#
# 装完会：① git clone whisper.cpp ② cmake 编译出 whisper-cli.exe
#         ③ 下载 ggml-base.bin 模型 ④ 写用户级环境变量 AOS_WHISPER_CPP_BIN / AOS_WHISPER_MODEL
# 重启终端后，AOS 的 STT 适配器会自动从 web_speech 切到 whisper_cpp（全离线）。
# =========================================================================
$ErrorActionPreference = "Stop"
$Root   = (Get-Item $PSScriptRoot).Parent.FullName          # D:\AOS
$Wcpp   = Join-Path $Root "whisper.cpp"
$BinDir = Join-Path $Wcpp "build\bin"
$Bin    = Join-Path $BinDir "whisper-cli.exe"
$Model  = Join-Path $Wcpp "models\ggml-base.bin"

Write-Host "==> 检查依赖"
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    Write-Error "缺少 cmake。请到 https://cmake.org/download/ 安装并加入 PATH。"
}
$cxx = (Get-Command cl -ErrorAction SilentlyContinue) -or (Get-Command gcc -ErrorAction SilentlyContinue)
if (-not $cxx) {
    Write-Error "缺少 C++ 编译器。请装 Visual Studio 2022（「使用 C++ 的桌面开发」）或 MinGW-w64。"
}
Write-Host "    cmake + 编译器 OK"

Write-Host "==> 克隆 whisper.cpp"
if (-not (Test-Path $Wcpp)) {
    git clone https://github.com/ggerganov/whisper.cpp $Wcpp
} else {
    Write-Host "    已存在，跳过 clone"
}

Write-Host "==> 编译（Release）"
if (-not (Test-Path $Bin)) {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    Push-Location $BinDir
    cmake $Wcpp
    cmake --build . --config Release
    Pop-Location
}
if (-not (Test-Path $Bin)) { Write-Error "编译失败：未生成 $Bin" }
Write-Host "    编译完成: $Bin"

Write-Host "==> 下载 ggml-base.bin 模型（约 140MB，首次需联网）"
if (-not (Test-Path $Model)) {
    & (Join-Path $Wcpp "models\download-ggml-model.cmd") base
}
if (-not (Test-Path $Model)) { Write-Error "模型下载失败，请手动执行 models\download-ggml-model.cmd base" }
Write-Host "    模型就绪: $Model"

Write-Host "==> 写入用户级环境变量（持久，重启终端生效）"
[Environment]::SetEnvironmentVariable("AOS_WHISPER_CPP_BIN", $Bin, "User")
[Environment]::SetEnvironmentVariable("AOS_WHISPER_MODEL", $Model, "User")

Write-Host ""
Write-Host "✅ whisper.cpp 全离线 STT 已装好。"
Write-Host "   重启 PowerShell 后，AOS STT 自动切到 whisper_cpp（不再依赖浏览器）。"
Write-Host "   验证：python -c ""from core.fabric.adapters.stt_adapter import STTAdapter; print(STTAdapter().health_detail())"""
Write-Host ""
Write-Host "💡 若只想最快全离线（无需编译），可直接：pip install faster-whisper"
Write-Host "   faster-whisper 是预编译 wheel，AOS 同样会自动识别并全离线运行。"
