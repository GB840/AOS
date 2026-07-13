# Index the whole AOS repo with the installed codebase-memory-mcp.
# Produces a committable, team-shared graph artifact.
#
# Prereq: run third_party/codebase-memory-mcp/install.ps1 first
#         (or have the binary on PATH / set AOS_CODEBASE_MCP_BIN).
# Non-source files are skipped via the repo-root .cbmignore (gitignore syntax).
#
# Mode note: we use --mode fast (filtered files, no similarity/semantic edges).
# The default 'full' mode runs cross-file similarity analysis that can hard-crash
# the v0.9.0 worker on certain files (it does not isolate the culprit file yet).
# 'fast' still produces full per-file + cross-file type-aware call/usage graphs,
# which is enough for architecture review. Artifact is written to:
#   D:/AOS/.codebase-memory/graph.db.zst
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin  = Join-Path $root 'third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe'
if (-not (Test-Path $bin)) { $bin = 'codebase-memory-mcp' }

Write-Host "Indexing AOS repo (fast mode): $root"
& $bin cli index_repository --repo-path $root --mode fast --persistence true
if ($LASTEXITCODE -ne 0) {
    Write-Error "Indexing failed (exit $LASTEXITCODE). Inspect C:/Users/Administrator/.cache/codebase-memory-mcp/logs/ , then add the culprit path to D:/AOS/.cbmignore and rerun."
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Commit the shared artifact so others can load it without re-indexing:"
Write-Host "  git add .codebase-memory/graph.db.zst"
Write-Host "  git commit -m 'chore: commit AOS code graph artifact (codebase-memory-mcp)'"
