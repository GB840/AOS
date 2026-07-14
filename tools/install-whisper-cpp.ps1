# =========================================================================
# AOS all-offline voice: install whisper.cpp (local STT, zero cloud dependency)
# Run in D:\AOS with PowerShell:
#   cd D:\AOS; powershell -ExecutionPolicy Bypass -File tools\install-whisper-cpp.ps1
#
# Prerequisites (script checks; exits with clear error if missing):
#   1) cmake         -- https://cmake.org/download/  (add bin to PATH)
#   2) C++ compiler  -- Visual Studio 2022 (Desktop development with C++) or MinGW-w64
#   3) git           -- usually present
#
# After install: 1) git clone whisper.cpp  2) cmake build whisper-cli.exe
#                3) download ggml-base.bin 4) write user env vars AOS_WHISPER_CPP_BIN / AOS_WHISPER_MODEL
# After restarting terminal, AOS STT auto-switches from web_speech to whisper_cpp (offline).
# =========================================================================
$ErrorActionPreference = "Stop"
$Root   = (Get-Item $PSScriptRoot).Parent.FullName          # D:\AOS
$Wcpp   = Join-Path $Root "whisper.cpp"
$BinDir = Join-Path $Wcpp "build\bin"
$Bin    = Join-Path $BinDir "whisper-cli.exe"
$Model  = Join-Path $Wcpp "models\ggml-base.bin"

Write-Host "==> checking prerequisites"
if (-not (Get-Command cmake -ErrorAction SilentlyContinue)) {
    Write-Error "cmake missing. Install from https://cmake.org/download/ and add to PATH."
}
$cxx = (Get-Command cl -ErrorAction SilentlyContinue) -or (Get-Command gcc -ErrorAction SilentlyContinue)
if (-not $cxx) {
    Write-Error "C++ compiler missing. Install Visual Studio 2022 (Desktop development with C++) or MinGW-w64."
}
Write-Host "    cmake + compiler OK"

Write-Host "==> cloning whisper.cpp"
if (-not (Test-Path $Wcpp)) {
    git clone https://github.com/ggerganov/whisper.cpp $Wcpp
} else {
    Write-Host "    already exists, skip clone"
}

Write-Host "==> building (Release)"
if (-not (Test-Path $Bin)) {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    cmake -S $Wcpp -B $BinDir
    cmake --build $BinDir --config Release
}
# locate the actual built exe (output path differs across cmake generators)
$BuiltExe = Get-ChildItem $Wcpp -Recurse -Include whisper-cli.exe,main.exe,whisper.exe | Select-Object -First 1
if (-not $BuiltExe) { Write-Error "build failed: whisper-cli.exe not found under $Wcpp" }
$Bin = $BuiltExe.FullName
Write-Host "    built: $Bin"

Write-Host "==> downloading ggml-base.bin model (about 140MB, needs network first time)"
if (-not (Test-Path $Model)) {
    & (Join-Path $Wcpp "models\download-ggml-model.cmd") base
}
if (-not (Test-Path $Model)) { Write-Error "model download failed; run models\download-ggml-model.cmd base manually" }
Write-Host "    model ready: $Model"

Write-Host "==> writing user-level environment variables (persist; restart terminal to take effect)"
[Environment]::SetEnvironmentVariable("AOS_WHISPER_CPP_BIN", $Bin, "User")
[Environment]::SetEnvironmentVariable("AOS_WHISPER_MODEL", $Model, "User")

Write-Host ""
Write-Host "[OK] whisper.cpp all-offline STT installed."
Write-Host "    After restarting PowerShell, AOS STT auto-switches to whisper_cpp (no browser needed)."
Write-Host "    Verify: python -c 'from core.fabric.adapters.stt_adapter import STTAdapter; print(STTAdapter().health_detail())'"
Write-Host ""
Write-Host "[TIP] For fastest offline (no compile): pip install faster-whisper"
Write-Host "    faster-whisper is a prebuilt wheel; AOS auto-detects and runs it fully offline too."
