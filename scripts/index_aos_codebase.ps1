# 用已安装的 codebase-memory-mcp 索引整个 AOS 仓库，并生成可提交的图工件。
#
# 前置：先运行 third_party/codebase-memory-mcp/install.ps1 把二进制装到 bin/，
#       或已通过 scoop/winget/npm 安装并在 PATH 中（或设 AOS_CODEBASE_MCP_BIN）。
#
# 产物：D:/AOS/.codebase-memory/graph.db.zst
#       这是「团队共享工件」，可 git add 提交，别人 clone 后直接加载、免全量重索引。
$ErrorActionPreference = 'Stop'

$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bin  = Join-Path $root 'third_party/codebase-memory-mcp/bin/codebase-memory-mcp.exe'
if (-not (Test-Path $bin)) { $bin = 'codebase-memory-mcp' }

Write-Host "索引 AOS 仓库: $root"
$arg = @{ repo_path = $root } | ConvertTo-Json -Compress
& $bin cli index_repository $arg
if ($LASTEXITCODE -ne 0) {
    Write-Error "索引失败（退出码 $LASTEXITCODE）。请确认二进制可用、仓库路径可访问。"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "完成。可提交共享工件供他人直接加载（跳过全量重索引）："
Write-Host "  git add .codebase-memory/graph.db.zst"
Write-Host "  git commit -m 'chore: 提交 AOS 代码图谱工件（codebase-memory-mcp）'"
