<#
.SYNOPSIS
Ollama Desktop Install Script

.DESCRIPTION
Install Ollama desktop version with friendly UI interface.
Desktop version provides model management, chat, API configuration.
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        Ollama Desktop Install Script" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$OLLAMA_URL = "https://ollama.com/download/OllamaSetup.exe"
$OLLAMA_INSTALLER = "$env:TEMP\OllamaSetup.exe"

Write-Host "`n[1/3] Checking Ollama..." -ForegroundColor Yellow
try {
    $ollamaVersion = ollama --version
    Write-Host "Ollama CLI already installed: $ollamaVersion" -ForegroundColor Green
}
catch {
    Write-Host "Ollama not installed" -ForegroundColor Red
}

Write-Host "`n[2/3] Downloading Ollama Desktop..." -ForegroundColor Yellow
Write-Host "Downloading from: $OLLAMA_URL" -ForegroundColor Gray

try {
    Invoke-WebRequest -Uri $OLLAMA_URL -OutFile $OLLAMA_INSTALLER -UseBasicParsing
    Write-Host "Download complete" -ForegroundColor Green
}
catch {
    Write-Host "Download failed, please download manually" -ForegroundColor Red
    Write-Host "Download URL: https://ollama.com/download" -ForegroundColor Gray
    exit 1
}

Write-Host "`n[3/3] Installing Ollama Desktop..." -ForegroundColor Yellow
Write-Host "Installing, please wait..." -ForegroundColor Gray

Start-Process $OLLAMA_INSTALLER -ArgumentList "/silent" -Wait -NoNewWindow
Remove-Item $OLLAMA_INSTALLER -Force

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "        Ollama Desktop Install Complete!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Install directory: C:\Users\$env:USERNAME\AppData\Local\Programs\Ollama" -ForegroundColor Green
Write-Host ""
Write-Host "First time setup:" -ForegroundColor Yellow
Write-Host "  1. Open Ollama Desktop app" -ForegroundColor Gray
Write-Host "  2. Register/Login account" -ForegroundColor Gray
Write-Host "  3. Select and download models from model list" -ForegroundColor Gray
Write-Host ""
Write-Host "Recommended models (8GB RAM):" -ForegroundColor Yellow
Write-Host "  - Qwen2.5:3B (recommended, ~2GB)" -ForegroundColor Gray
Write-Host "  - Qwen2.5:7B (~4.5GB)" -ForegroundColor Gray
Write-Host "  - Llama 3.3:8B (~4.5GB)" -ForegroundColor Gray
Write-Host ""
Write-Host "CLI verification:" -ForegroundColor Yellow
Write-Host "  ollama list          # List installed models" -ForegroundColor White
Write-Host "  ollama pull qwen2.5:3b  # Pull model" -ForegroundColor White
Write-Host "  ollama run qwen2.5:3b   # Run model" -ForegroundColor White
Write-Host ""
Write-Host "Integration with AOS:" -ForegroundColor Yellow
Write-Host "  - Start Ollama Desktop, AOS will auto-connect" -ForegroundColor Gray
Write-Host "  - Default port: 11434" -ForegroundColor Gray