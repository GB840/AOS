# Pull the real codebase-memory-mcp binary into third_party/codebase-memory-mcp/bin/
# After this, AOS auto-registers code.understanding on startup (no code change needed).
# If network fails, the script prints manual options; or install via scoop/winget/npm and set AOS_CODEBASE_MCP_BIN.
$ErrorActionPreference = 'Stop'
$Repo   = 'DeusData/codebase-memory-mcp'
$Dest   = Join-Path $PSScriptRoot 'bin'
New-Item -ItemType Directory -Force -Path $Dest | Out-Null

function Find-WindowsAsset($rel) {
    $rel.assets | Where-Object { $_.name -match 'win' -and ($_.name -match '\.zip$' -or $_.name -match '\.exe$') } | Select-Object -First 1
}

try {
    Write-Host "Query latest release: https://api.github.com/repos/$Repo/releases/latest"
    $rel   = Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'aos' }
    $asset = Find-WindowsAsset $rel
    if (-not $asset) {
        $asset = $rel.assets | Where-Object { $_.name -match '\.exe$' -or $_.name -match '\.zip$' } | Select-Object -First 1
    }
    if (-not $asset) { throw "No Windows asset found in release" }

    $url = $asset.browser_download_url
    Write-Host "Download: $($asset.name)  <-  $url"
    $destFile = Join-Path $Dest $asset.name
    Invoke-WebRequest -Uri $url -OutFile $destFile

    if ($destFile -match '\.zip$') {
        Expand-Archive -Path $destFile -DestinationPath $Dest -Force
        Remove-Item $destFile
    }

    $exe = Get-ChildItem $Dest -Filter 'codebase-memory-mcp.exe' -Recurse | Select-Object -First 1
    if (-not $exe) {
        Write-Warning "codebase-memory-mcp.exe not found under bin/ after extraction. Check bin/ and place it manually."
        exit 1
    }
    Write-Host "Ready: $($exe.FullName)"
    Write-Host "AOS will auto-register code.understanding on next startup."
    Write-Host "Then run scripts/index_aos_codebase.ps1 to index the whole AOS repo."
}
catch {
    Write-Warning "Auto-install failed: $_"
    Write-Host ""
    Write-Host "Manual options (then place the binary into the bin/ folder):"
    Write-Host "  1) scoop install codebase-memory-mcp"
    Write-Host "  2) winget install DeusData.codebase-memory-mcp"
    Write-Host "  3) npm i -g codebase-memory-mcp"
    Write-Host "  4) Download Windows zip from https://github.com/$Repo/releases/latest and extract"
    Write-Host "  5) Build from source: git clone https://github.com/$Repo ; cd codebase-memory-mcp ; scripts/build.sh"
    Write-Host "After placing (or set AOS_CODEBASE_MCP_BIN to it), AOS auto-enables on startup."
    exit 1
}
