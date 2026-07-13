# One-click: install the real codebase-memory-mcp binary into AOS and index the whole repo.
#
# It does two things (same as the two steps you saw before):
#   Step 1  third_party/codebase-memory-mcp/install.ps1  - download the 37MB pure-C binary into bin/
#   Step 2  scripts/index_aos_codebase.ps1               - scan the whole AOS, build the code graph
#
# Usage (from repo root D:\AOS, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File setup_codebase_memory.ps1
#
# After it finishes:
#   - AOS auto-enables the code.understanding capability on startup (no code change needed)
#   - artifact .codebase-memory/graph.db.zst is committable; others clone and load it directly (no full re-index)
$ErrorActionPreference = 'Continue'   # we control the flow; result-based checks below

$root           = $PSScriptRoot
$installScript  = Join-Path $root 'third_party/codebase-memory-mcp/install.ps1'
$indexScript    = Join-Path $root 'scripts/index_aos_codebase.ps1'
$binExpected    = Join-Path $root 'third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe'

function Write-Step($n, $msg, $color) {
    Write-Host ("[{0}/2] {1}" -f $n, $msg) -ForegroundColor $color
}

Write-Host "=== AOS - codebase-memory-mcp one-click setup ===" -ForegroundColor Cyan
Write-Host "Repo root: $root"

# ---------- Step 1: download the binary ----------
if (Test-Path $binExpected) {
    Write-Step 1 "Binary already present, skip download: $binExpected" Green
}
else {
    Write-Step 1 "Downloading real codebase-memory-mcp binary (~37MB)..." Yellow
    & "$installScript"
    # Result-based check: did the binary actually land? (not relying on exit-code semantics)
    $binOK = (Test-Path $binExpected) -or (Get-Command codebase-memory-mcp -ErrorAction SilentlyContinue)
    if (-not $binOK) {
        Write-Host ""
        Write-Error "Binary not found after install. Network may be restricted. Follow install.ps1 hints to install manually (scoop/winget/npm, or drop the exe into bin/), then rerun this script or run step 2 directly."
        exit 1
    }
    Write-Host "Binary ready." Green
}

# ---------- Step 2: scan and build the graph ----------
Write-Step 2 "Indexing the entire AOS repo, building code knowledge graph (may take tens of seconds to a few minutes)..." Yellow
& "$indexScript"
$indexOK = (Test-Path (Join-Path $root '.codebase-memory/graph.db.zst')) -or ($LASTEXITCODE -eq 0)
if (-not $indexOK) {
    Write-Host ""
    Write-Error "Indexing did not produce the artifact (exit $LASTEXITCODE). Confirm the binary works, or run manually: $indexScript"
    exit 1
}

Write-Host ""
Write-Host "=== DONE ===" -ForegroundColor Green
Write-Host "AOS now has code.understanding capability; it loads the binary automatically on startup."
$graphPath = Join-Path $root '.codebase-memory/graph.db.zst'
if (Test-Path $graphPath) {
    Write-Host "Shared graph artifact generated: $graphPath"
    Write-Host "Commit it so others can load directly (skip full re-index):"
    Write-Host "    git add .codebase-memory/graph.db.zst"
    Write-Host "    git commit -m 'chore: commit AOS code graph artifact (codebase-memory-mcp)'"
}
