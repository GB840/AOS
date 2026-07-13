# 把真实 codebase-memory-mcp 二进制拉进仓库 third_party/codebase-memory-mcp/bin/
# 装好后 AOS 启动时 FabricHub 会自动注册 code.understanding 能力（无需改代码）。
# 网络不通时脚本会给出手动放置提示；也可改用 scoop/winget/npm 安装后设 AOS_CODEBASE_MCP_BIN。
$ErrorActionPreference = 'Stop'
$Repo   = 'DeusData/codebase-memory-mcp'
$Dest   = Join-Path $PSScriptRoot 'bin'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

function Find-WindowsAsset($rel) {
    # 优先含 win/windows 且为 zip/exe 的资产；找不到再放宽到任何含 exe/zip 的。
    $rel.assets | Where-Object { $_.name -match 'win' -and ($_.name -match '\.zip$' -or $_.name -match '\.exe$') } | Select-Object -First 1
}

try {
    Write-Host "查询最新 release: https://api.github.com/repos/$Repo/releases/latest"
    $rel   = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'aos' }
    $asset = Find-WindowsAsset $rel
    if (-not $asset) {
        $asset = $rel.assets | Where-Object { $_.name -match '\.exe$' -or $_.name -match '\.zip$' } | Select-Object -First 1
    }
    if (-not $asset) { throw "release 中未找到 Windows 资产" }

    $url = $asset.browser_download_url
    Write-Host "下载: $($asset.name)  <-  $url"
    $destFile = Join-Path $Dest $asset.name
    Invoke-WebRequest -Uri $url -OutFile $destFile

    if ($destFile -match '\.zip$') {
        Expand-Archive -Path $destFile -DestinationPath $Dest -Force
        Remove-Item $destFile
    }

    $exe = Get-ChildItem $Dest -Filter 'codebase-memory-mcp.exe' -Recurse | Select-Object -First 1
    if (-not $exe) {
        Write-Warning "解压后未在 bin/ 下找到 codebase-memory-mcp.exe，请检查 bin/ 内容并手动放置。"
        exit 1
    }
    Write-Host "已就位: $($exe.FullName)"
    Write-Host "AOS 现在会在启动时自动注册 code.understanding 能力（重启 AOS 进程即可生效）。"
    Write-Host "随后运行 scripts/index_aos_codebase.ps1 索引整个 AOS 仓库。"
}
catch {
    Write-Warning "自动安装失败: $_"
    Write-Host ""
    Write-Host "可改用手动方式之一，然后把二进制放到: $Dest\codebase-memory-mcp.exe"
    Write-Host "  1) scoop install codebase-memory-mcp"
    Write-Host "  2) winget install DeusData.codebase-memory-mcp"
    Write-Host "  3) npm i -g codebase-memory-mcp"
    Write-Host "  4) 从 https://github.com/$Repo/releases/latest 下载 Windows 压缩包解压"
    Write-Host "  5) 源码构建: git clone https://github.com/$Repo ; cd codebase-memory-mcp ; scripts/build.sh"
    Write-Host "放好后（或设 AOS_CODEBASE_MCP_BIN 指向它），AOS 启动时即自动通电。"
    exit 1
}
