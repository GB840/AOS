<#
.SYNOPSIS
Create Ollama Modelfiles for GGUF models

.DESCRIPTION
Create Modelfiles that allow Ollama to use GGUF models from Llama.cpp.
This enables the unified API gateway pattern:
Ollama API -> GGUF models -> Llama.cpp inference

Fallback tiers:
- HIGH: qwen2.5-3b (~2GB) - Complex tasks
- MEDIUM: qwen2.5-1.5b (~1GB) - Balanced (recommended)
- LOW: qwen2.5-0.5b (~400MB) - Fast/simple tasks
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        Create Ollama Modelfiles" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$MODELS_DIR = "D:\llama.cpp\models"
$MODelfILE_DIR = "D:\llama.cpp\modelfiles"

New-Item -ItemType Directory -Path $MODelfILE_DIR -Force | Out-Null

$MODELS = @(
    @{
        Name = "qwen2.5-0.5b";
        OllamaName = "qwen2.5-0.5b";
        GGUFPath = "$MODELS_DIR\qwen2.5-0.5b-q4_k_m.gguf";
        Tier = "LOW";
        ContextWindow = 2048;
        NumThreads = 4;
        Description = "Fastest, ~400MB"
    },
    @{
        Name = "qwen2.5-1.5b";
        OllamaName = "qwen2.5-1.5b";
        GGUFPath = "$MODELS_DIR\qwen2.5-1.5b-q4_k_m.gguf";
        Tier = "MEDIUM";
        ContextWindow = 2048;
        NumThreads = 4;
        Description = "Balanced, ~1GB (recommended)"
    },
    @{
        Name = "qwen2.5-3b";
        OllamaName = "qwen2.5-3b";
        GGUFPath = "$MODELS_DIR\qwen2.5-3b-q4_k_m.gguf";
        Tier = "HIGH";
        ContextWindow = 2048;
        NumThreads = 4;
        Description = "Strongest, ~2GB"
    }
)

Write-Host "`nCreating Modelfiles..." -ForegroundColor Yellow

foreach ($model in $MODELS) {
    $modelfilePath = Join-Path $MODelfILE_DIR "$($model.Name).Modelfile"
    
    $modelfileContent = @"
FROM $($model.GGUFPath)
PARAMETER num_thread $($model.NumThreads)
PARAMETER context_window $($model.ContextWindow)
PARAMETER stop "<|endoftext|>"
SYSTEM You are Qwen, created by Alibaba Cloud. You are a helpful assistant.
"@
    
    Set-Content -Path $modelfilePath -Value $modelfileContent -Encoding UTF8
    Write-Host "✓ $($model.Name).Modelfile created" -ForegroundColor Green
    
    if (Test-Path $model.GGUFPath) {
        Write-Host "  GGUF file exists: $(Get-Item $model.GGUFPath).Length / 1MB -f 'N1') MB" -ForegroundColor Gray
    }
    else {
        Write-Host "  ⚠️ GGUF file not found: $($model.GGUFPath)" -ForegroundColor Yellow
    }
}

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "        Modelfiles Created!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "To create Ollama models from GGUF:" -ForegroundColor Yellow

foreach ($model in $MODELS) {
    Write-Host ""
    Write-Host "[$($model.Tier)] $($model.Name)" -ForegroundColor Cyan
    Write-Host "  Description: $($model.Description)" -ForegroundColor Gray
    Write-Host "  Command:" -ForegroundColor Gray
    Write-Host "    cd D:\llama.cpp\modelfiles" -ForegroundColor White
    Write-Host "    ollama create $($model.OllamaName) -f $($model.Name).Modelfile" -ForegroundColor White
}

Write-Host ""
Write-Host "Fallback mechanism:" -ForegroundColor Yellow
Write-Host "  HIGH (3B) → MEDIUM (1.5B) → LOW (0.5B)" -ForegroundColor Gray
Write-Host ""
Write-Host "Usage:" -ForegroundColor Yellow
Write-Host "  ollama run qwen2.5-1.5b" -ForegroundColor White
Write-Host "  curl http://localhost:11434/api/generate -d '{""model"": ""qwen2.5-1.5b"", ""prompt"": ""Hello""}'" -ForegroundColor White