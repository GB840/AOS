<#
.SYNOPSIS
  下载 LFM2 真权重到本地，并配置 AOS 使用它（实现「LFM2 真权重」）。
.DESCRIPTION
  AOS 的 LFMAdapter 默认不谎报 live：没装权重时自动退回其它 LLM 供给方。
  本脚本把 LFM2 开放权重拉到本地，并设好 AOS_LFM_MODEL，让 LFM2 成为
  真正可用的「边缘低功耗」LLM 一极（高低搭配路由生效）。

  两种后端（二选一）：
    - transformers（默认）：下载 safetensors，需 torch+transformers（已装）。
    - llama_cpp（GGUF）：下载 .gguf，需 pip install llama-cpp-python，CPU/GPU 通吃、最省。

  注意：HuggingFace 在国内偶发被墙。若 huggingface-cli 下载慢/失败，可设镜像：
    $env:HF_ENDPOINT = "https://hf-mirror.com"
.EXAMPLE
  # 默认：下载 LFM2.5-230M（transformers safetensors）
  powershell -ExecutionPolicy Bypass -File fetch-lfm2.ps1

  # 用 GGUF（llama.cpp）后端，更小更快
  powershell -ExecutionPolicy Bypass -File fetch-lfm2.ps1 -GGUF

  # 指定其它 LFM2 变体
  powershell -ExecutionPolicy Bypass -File fetch-lfm2.ps1 -Model "LiquidAI/LFM2-450M"
#>
param(
    [string]$Model = "LiquidAI/LFM2.5-230M",
    [string]$OutDir = "",
    [switch]$GGUF
)

$ErrorActionPreference = "Stop"

if (-not $OutDir) {
    $OutDir = Join-Path $PSScriptRoot ".." "models" "lfm2"
}
$OutDir = Resolve-Path -LiteralPath $OutDir -ErrorAction SilentlyContinue
if (-not $OutDir) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$OutDir = Resolve-Path -LiteralPath $OutDir

Write-Host "[fetch-lfm2] 目标模型: $Model" -ForegroundColor Cyan
Write-Host "[fetch-lfm2] 输出目录: $OutDir" -ForegroundColor Cyan

# 1) 确保 huggingface_hub CLI 可用
try {
    huggingface-cli --version | Out-Null
    Write-Host "[fetch-lfm2] huggingface-cli 已就绪" -ForegroundColor Green
} catch {
    Write-Host "[fetch-lfm2] 安装 huggingface_hub[cli] ..." -ForegroundColor Yellow
    python -m pip install -U "huggingface_hub[cli]"
}

# 2) 构造下载参数
$cliArgs = @("download", $Model, "--local-dir", $OutDir)
if ($GGUF) {
    # GGUF 仓库通常是 <Model>-GGUF，且只需 .gguf 文件
    if ($Model -notlike "*-GGUF") { $Model = "$Model-GGUF" }
    $cliArgs = @("download", $Model, "--include", "*.gguf", "--local-dir", $OutDir)
    Write-Host "[fetch-lfm2] 后端=llama_cpp(GGUF)，目标: $Model" -ForegroundColor Cyan
} else {
    Write-Host "[fetch-lfm2] 后端=transformers(safetensors)" -ForegroundColor Cyan
}

Write-Host "[fetch-lfm2] 开始下载（若被墙请先: `$env:HF_ENDPOINT='https://hf-mirror.com'）..." -ForegroundColor Yellow
huggingface-cli @cliArgs

# 3) 选定权重路径并写环境变量
$weightsPath = $null
if ($GGUF) {
    $gguf = Get-ChildItem -Path $OutDir -Filter *.gguf | Select-Object -First 1
    if ($gguf) { $weightsPath = $gguf.FullName }
} else {
    $index = Get-ChildItem -Path $OutDir -Filter "*.safetensors" | Select-Object -First 1
    if ($index) { $weightsPath = $OutDir }
}

if (-not $weightsPath) {
    Write-Host "[fetch-lfm2] 未找到预期权重文件，请检查下载结果。" -ForegroundColor Red
    exit 1
}

# 写进项目 .env（不覆盖已有 AOS_LFM_MODEL）
$envPath = Join-Path $PSScriptRoot ".." ".env"
$line = "AOS_LFM_MODEL=$weightsPath"
if (Test-Path $envPath) {
    $content = Get-Content $envPath -Raw
    if ($content -match "AOS_LFM_MODEL=") {
        Write-Host "[fetch-lfm2] .env 已存在 AOS_LFM_MODEL，未覆盖；如需改请手动编辑: $envPath" -ForegroundColor Yellow
    } else {
        Add-Content -Path $envPath -Value $line
        Write-Host "[fetch-lfm2] 已追加到 .env: $line" -ForegroundColor Green
    }
} else {
    Set-Content -Path $envPath -Value $line
    Write-Host "[fetch-lfm2] 已写入 .env: $line" -ForegroundColor Green
}

if ($GGUF) {
    Write-Host "[fetch-lfm2] GGUF 还需: pip install llama-cpp-python" -ForegroundColor Yellow
    Write-Host "[fetch-lfm2] 并设 AOS_LFM_BACKEND=llama_cpp（已用 GGUF 时建议加）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[fetch-lfm2] 完成 ✅ 重启 AOS 服务后，GET /api/lnn/info 的 lfm2.live 应为 true。" -ForegroundColor Green
Write-Host "[fetch-lfm2] 验证: python -c `"from core.fabric.adapters.lfm_adapter import LFMAdapter; print(LFMAdapter().health())`"" -ForegroundColor Green
