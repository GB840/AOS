<#
.SYNOPSIS
Start the AOS platform via the unified supervisor.

.DESCRIPTION
The AOS platform is composed of four long-running services:
  - DeerFlow gateway   (:2026)
  - AOS API + gateway  (:8000, single entry port)
  - Web console        (:8501, served under /web)
  - OpenClaw gateway   (:18789)

This script is a thin Windows wrapper around the cross-platform supervisor
(scripts/aos_supervisor.py), which starts them in dependency order, gates each
on a health check, supervises them (auto-restart on death), and shuts them down
cleanly on Ctrl+C.

Examples:
  .\scripts\start_aos.ps1            # start full stack, stay up (supervised)
  .\scripts\start_aos.ps1 -Check     # print health of every service, exit
  .\scripts\start_aos.ps1 -Stop      # stop everything started here
  .\scripts\start_aos.ps1 -Only aos  # start only the AOS API
#>

[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Stop,
    [string[]]$Only,
    [string[]]$Skip
)

$ErrorActionPreference = "Stop"

# Resolve the AOS venv python (override with $env:AOS_VENV if needed).
if ($env:AOS_VENV -and (Test-Path $env:AOS_VENV)) {
    $Py = $env:AOS_VENV
} else {
    $Py = "C:\Users\Administrator\.workbuddy\binaries\python\envs\aos\Scripts\python.exe"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AOSRoot = Split-Path -Parent $ScriptDir
$Supervisor = Join-Path $ScriptDir "aos_supervisor.py"

if (-not (Test-Path $Py)) {
    Write-Error "AOS venv python not found at: $Py`nSet `$env:AOS_VENV to your venv's python.exe"
    exit 1
}

$args = @()
if ($Check)     { $args += "--check" }
if ($Stop)      { $args += "--stop" }
if ($Only)      { $args += "--only"; $args += $Only }
if ($Skip)      { $args += "--skip"; $args += $Skip }

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "        AOS Platform (unified supervisor)" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Root : $AOSRoot"
Write-Host "Py   : $Py"
Write-Host "Args : $($args -join ' ')"
Write-Host ""

& $Py $Supervisor @args
