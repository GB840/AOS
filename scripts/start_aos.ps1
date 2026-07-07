<#
.SYNOPSIS
Start AOS AI Platform with all services

.DESCRIPTION
Start AOS with:
1. Ollama service (if not running)
2. Llama.cpp server (if GGUF models available)
3. AOS Web application (Streamlit)

Fallback mechanism:
- HIGH: qwen2.5-3b (~2GB)
- MEDIUM: qwen2.5-1.5b (~1GB) - Recommended
- LOW: qwen2.5-0.5b (~400MB)
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        Start AOS AI Platform" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

function Test-Ollama {
    try {
        $result = & ollama --version 2>&1
        return $true
    }
    catch {
        return $false
    }
}

function Test-LlamaCpp {
    $serverPath = "D:\llama.cpp\llama-server.exe"
    return Test-Path $serverPath
}

function Start-OllamaService {
    Write-Host "`n[1/3] Starting Ollama service..." -ForegroundColor Yellow
    
    try {
        $result = & ollama serve 2>&1
        Write-Host "Ollama service started" -ForegroundColor Green
        return $true
    }
    catch {
        Write-Host "Ollama service may already be running" -ForegroundColor Yellow
        return $true
    }
}

function Start-LlamaCpp {
    Write-Host "`n[2/3] Starting Llama.cpp server..." -ForegroundColor Yellow
    
    $modelsDir = "D:\llama.cpp\models"
    $models = @(
        @{Name="qwen2.5-3b"; Tier="HIGH"; Size="~2GB"},
        @{Name="qwen2.5-1.5b"; Tier="MEDIUM"; Size="~1GB"},
        @{Name="qwen2.5-0.5b"; Tier="LOW"; Size="~400MB"}
    )
    
    foreach ($model in $models) {
        $modelFile = Get-ChildItem -Path $modelsDir -Filter "*$($model.Name)*.gguf" -ErrorAction SilentlyContinue
        if ($modelFile) {
            Write-Host "[$($model.Tier)] Starting with $($model.Name) ($($model.Size))" -ForegroundColor Cyan
            
            $cmd = "D:\llama.cpp\llama-server.exe -m `"$($modelFile.FullName)`" -c 2048 --host 0.0.0.0 --port 8080 -t 4 -ngl 0"
            Write-Host "Command: $cmd" -ForegroundColor Gray
            
            Start-Process -FilePath "D:\llama.cpp\llama-server.exe" -ArgumentList @(
                "-m", $modelFile.FullName,
                "-c", "2048",
                "--host", "0.0.0.0",
                "--port", "8080",
                "-t", "4",
                "-ngl", "0"
            ) -WorkingDirectory "D:\llama.cpp"
            
            Start-Sleep -Seconds 5
            
            try {
                $resp = Invoke-WebRequest -Uri "http://localhost:8080/health" -UseBasicParsing -TimeoutSec 5
                if ($resp.StatusCode -eq 200) {
                    Write-Host "Llama.cpp server started successfully on port 8080" -ForegroundColor Green
                    return $true
                }
            }
            catch {
                Write-Host "Llama.cpp server failed to start, trying next model..." -ForegroundColor Yellow
            }
        }
        else {
            Write-Host "[$($model.Tier)] $($model.Name) model not found" -ForegroundColor Gray
        }
    }
    
    Write-Host "No GGUF models found, using Ollama as fallback" -ForegroundColor Yellow
    return $false
}

function Start-AOS {
    Write-Host "`n[3/3] Starting AOS Web application..." -ForegroundColor Yellow
    
    Set-Location "D:\AOS"
    Start-Process -FilePath "python" -ArgumentList @("-m", "streamlit", "run", "src/web/app.py") -WorkingDirectory "D:\AOS"
    
    Write-Host "AOS Web application starting..." -ForegroundColor Green
    Write-Host "Open browser: http://localhost:8501" -ForegroundColor White
}

Write-Host "`nChecking dependencies..." -ForegroundColor Yellow

$ollamaReady = Test-Ollama
$llamaCppReady = Test-LlamaCpp

if ($ollamaReady) {
    Write-Host "✓ Ollama: Available" -ForegroundColor Green
}
else {
    Write-Host "✗ Ollama: Not installed" -ForegroundColor Red
}

if ($llamaCppReady) {
    Write-Host "✓ Llama.cpp: Available" -ForegroundColor Green
}
else {
    Write-Host "✗ Llama.cpp: Not installed" -ForegroundColor Red
}

Write-Host "`nChecking Ollama models..." -ForegroundColor Yellow
try {
    $ollamaList = & ollama list 2>&1
    $models = $ollamaList | Select-Object -Skip 1
    if ($models) {
        foreach ($model in $models) {
            $parts = $model -split '\s+' | Where-Object { $_ }
            if ($parts.Count -ge 3) {
                Write-Host "  ✓ $($parts[0]) - $($parts[2])" -ForegroundColor Green
            }
        }
    }
}
catch {
    Write-Host "  No Ollama models found" -ForegroundColor Gray
}

Write-Host "`nChecking GGUF models..." -ForegroundColor Yellow
try {
    $ggufFiles = Get-ChildItem -Path "D:\llama.cpp\models" -Filter "*.gguf" -ErrorAction SilentlyContinue
    if ($ggufFiles) {
        foreach ($file in $ggufFiles) {
            $size = $file.Length / 1MB
            Write-Host "  ✓ $($file.Name) - $($size.ToString('N1')) MB" -ForegroundColor Green
        }
    }
    else {
        Write-Host "  No GGUF models found" -ForegroundColor Gray
    }
}
catch {
    Write-Host "  GGUF models directory not found" -ForegroundColor Gray
}

Start-OllamaService
Start-LlamaCpp
Start-AOS

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "        AOS Platform Started!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services:" -ForegroundColor Yellow
Write-Host "  - Ollama API: http://localhost:11434" -ForegroundColor Gray
Write-Host "  - Llama.cpp API: http://localhost:8080 (if running)" -ForegroundColor Gray
Write-Host "  - AOS Web: http://localhost:8501" -ForegroundColor Gray
Write-Host ""
Write-Host "Fallback mechanism:" -ForegroundColor Yellow
Write-Host "  HIGH (3B) → MEDIUM (1.5B) → LOW (0.5B) → Ollama" -ForegroundColor Gray