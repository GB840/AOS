# 停止所有 MistralRS 本地模型服务
$ports = @(1234, 1235, 1236)
foreach ($p in $ports) {
    $procs = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($pid_ in $procs) {
        if ($pid_ -and $pid_ -ne 0) {
            Write-Host "Stopping PID $pid_ on port $p ..."
            Stop-Process -Id $pid_ -Force -ErrorAction SilentlyContinue
        }
    }
}
# 兜底：按进程名杀
Get-Process -Name "mistralrs" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "Stopping mistralrs.exe PID $($_.Id) ..."
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}
Write-Host "Done."
