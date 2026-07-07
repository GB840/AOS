<#
.SYNOPSIS
Download GGUF models for Llama.cpp

.DESCRIPTION
Download Qwen2.5 GGUF models from Hugging Face.
Supports three tiers for fallback mechanism:
- LOW: Qwen2.5-0.5B (~400MB) - Fastest, for simple tasks
- MEDIUM: Qwen2.5-1.5B (~1GB) - Balanced, recommended
- HIGH: Qwen2.5-3B (~2GB) - Strongest, for complex tasks

Total size: ~3.4GB - fits in 8GB RAM
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        Download GGUF Models" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$MODELS_DIR = "D:\llama.cpp\models"

$MODELS = @(
    @{
        Name = "qwen2.5-0.5b";
        URL = "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf";
        Size = "~400MB";
        Tier = "LOW";
        Description = "Fastest, for simple tasks"
    },
    @{
        Name = "qwen2.5-1.5b";
        URL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf";
        Size = "~1GB";
        Tier = "MEDIUM";
        Description = "Balanced, recommended"
    },
    @{
        Name = "qwen2.5-3b";
        URL = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf";
        Size = "~2GB";
        Tier = "HIGH";
        Description = "Strongest, for complex tasks"
    }
)

Write-Host "`nAvailable models:" -ForegroundColor Yellow
foreach ($model in $MODELS) {
    Write-Host "  [$($model.Tier)] $($model.Name) - $($model.Size) - $($model.Description)" -ForegroundColor Gray
}

foreach ($model in $MODELS) {
    $modelFile = "$($model.Name)-q4_k_m.gguf"
    $modelPath = Join-Path $MODELS_DIR $modelFile
    
    if (Test-Path $modelPath) {
        Write-Host "`n[SKIP] $($model.Name) already exists" -ForegroundColor Yellow
        continue
    }
    
    Write-Host "`n[DOWNLOAD] $($model.Tier): $($model.Name) ($($model.Size))" -ForegroundColor Cyan
    Write-Host "URL: $($model.URL)" -ForegroundColor Gray
    
    try {
        Invoke-WebRequest -Uri $model.URL -OutFile $modelPath -UseBasicParsing
        Write-Host "Download completed" -ForegroundColor Green
    }
    catch {
        Write-Host "Download failed: $_" -ForegroundColor Red
        Write-Host "Trying mirror..." -ForegroundColor Yellow
        
        try {
            $mirrorURL = $model.URL -replace "huggingface.co", "hf-mirror.com"
            Write-Host "Mirror URL: $mirrorURL" -ForegroundColor Gray
            Invoke-WebRequest -Uri $mirrorURL -OutFile $modelPath -UseBasicParsing
            Write-Host "Download completed via mirror" -ForegroundColor Green
        }
        catch {
            Write-Host "Mirror download failed: $_" -ForegroundColor Red
        }
    }
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "        Download Complete!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$totalSize = 0
$count = 0
foreach ($model in $MODELS) {
    $modelFile = "$($model.Name)-q4_k_m.gguf"
    $modelPath = Join-Path $MODELS_DIR $modelFile
    if (Test-Path $modelPath) {
        $size = (Get-Item $modelPath).Length / (1MB)
        $totalSize += $size
        $count++
        Write-Host "✓ $($modelFile): $($size.ToString('N1')) MB" -ForegroundColor Green
    }
    else {
        Write-Host "✗ $($modelFile): Not found" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "Total: $count models, $($totalSize.ToString('N1')) MB" -ForegroundColor Yellow
Write-Host ""
Write-Host "Fallback mechanism:" -ForegroundColor Yellow
Write-Host "  HIGH (3B) → MEDIUM (1.5B) → LOW (0.5B)" -ForegroundColor Gray
Write-Host ""
Write-Host "Start Llama.cpp server:" -ForegroundColor Yellow
Write-Host "  cd D:\llama.cpp" -ForegroundColor White
Write-Host "  .\llama-server.exe -m models\qwen2.5-1.5b-q4_k_m.gguf -c 2048 --host 0.0.0.0 --port 8080" -ForegroundColor White