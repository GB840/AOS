<#
.SYNOPSIS
UI-TARS Install Script

.DESCRIPTION
Install UI-TARS desktop version:
1. Check and install Node.js
2. Clone UI-TARS source code
3. Install dependencies
4. Create startup shortcuts

Requires network access to GitHub and npm repositories
#>

$ErrorActionPreference = "Stop"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        UI-TARS Install Script v1.0" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan

$UITARS_DIR = "D:\UI-TARS-desktop"
$NODE_URL = "https://nodejs.org/dist/v20.12.0/node-v20.12.0-x64.msi"
$NODE_INSTALLER = "$env:TEMP\node-installer.msi"

# Check Node.js
Write-Host "`n[1/4] Checking Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version
    Write-Host "Node.js already installed: $nodeVersion" -ForegroundColor Green
}
catch {
    Write-Host "Node.js not found, downloading..." -ForegroundColor Red
    
    Write-Host "Downloading Node.js 20.x..." -ForegroundColor Gray
    Invoke-WebRequest -Uri $NODE_URL -OutFile $NODE_INSTALLER -UseBasicParsing
    
    Write-Host "Installing Node.js..." -ForegroundColor Gray
    Start-Process msiexec -ArgumentList "/i `"$NODE_INSTALLER`" /qn /norestart" -Wait -NoNewWindow
    
    Remove-Item $NODE_INSTALLER -Force
    Write-Host "Node.js installed successfully" -ForegroundColor Green
    
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# Check Git
Write-Host "`n[2/4] Checking Git..." -ForegroundColor Yellow
try {
    $gitVersion = git --version
    Write-Host "Git already installed: $gitVersion" -ForegroundColor Green
}
catch {
    Write-Host "Git not found, please install Git first" -ForegroundColor Red
    Write-Host "Download URL: https://git-scm.com/download/win" -ForegroundColor Gray
    exit 1
}

# Clone UI-TARS
Write-Host "`n[3/4] Cloning UI-TARS source..." -ForegroundColor Yellow
if (Test-Path $UITARS_DIR) {
    Write-Host "UI-TARS directory exists, skipping clone" -ForegroundColor Yellow
}
else {
    Write-Host "Cloning UI-TARS-desktop..." -ForegroundColor Gray
    
    $repos = @(
        "https://github.com/bytedance/UI-TARS-desktop.git",
        "https://gitclone.com/github.com/bytedance/UI-TARS-desktop.git",
        "https://hub.fastgit.xyz/bytedance/UI-TARS-desktop.git"
    )
    
    $success = $false
    foreach ($repo in $repos) {
        try {
            Write-Host "Trying: $repo" -ForegroundColor Gray
            git clone $repo $UITARS_DIR
            if (Test-Path $UITARS_DIR) {
                $success = $true
                Write-Host "Clone successful" -ForegroundColor Green
                break
            }
        }
        catch {
            Write-Host "Clone failed: $_" -ForegroundColor Red
        }
    }
    
    if (-not $success) {
        Write-Host "All repositories unavailable, please download manually" -ForegroundColor Red
        Write-Host "Download URL: https://github.com/bytedance/UI-TARS-desktop/releases" -ForegroundColor Gray
        exit 1
    }
}

# Install dependencies
Write-Host "`n[4/4] Installing dependencies..." -ForegroundColor Yellow
Set-Location $UITARS_DIR

try {
    $pnpmVersion = pnpm --version
    Write-Host "pnpm already installed: $pnpmVersion" -ForegroundColor Green
}
catch {
    Write-Host "Installing pnpm..." -ForegroundColor Gray
    npm install -g pnpm
}

Write-Host "Installing project dependencies..." -ForegroundColor Gray
pnpm install

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "        UI-TARS Install Complete!" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Install directory: $UITARS_DIR" -ForegroundColor Green
Write-Host ""
Write-Host "Startup options:" -ForegroundColor Yellow
Write-Host "  1. Desktop App:" -ForegroundColor Gray
Write-Host "     cd $UITARS_DIR\apps\ui-tars" -ForegroundColor White
Write-Host "     pnpm run dev" -ForegroundColor White
Write-Host ""
Write-Host "  2. CLI Mode:" -ForegroundColor Gray
Write-Host "     cd $UITARS_DIR" -ForegroundColor White
Write-Host "     pnpm run cli" -ForegroundColor White
Write-Host ""
Write-Host "  3. MCP Mode:" -ForegroundColor Gray
Write-Host "     cd $UITARS_DIR" -ForegroundColor White
Write-Host "     pnpm run mcp" -ForegroundColor White
Write-Host ""
Write-Host "Config file: $UITARS_DIR\apps\ui-tars\.env" -ForegroundColor Gray
Write-Host "API Key: Need to configure multimodal model API Key" -ForegroundColor Gray