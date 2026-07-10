# 停掉三个 mistralrs serve 进程（按监听端口 1234/1235/1236 反查 PID 后结束）。
$ports = @(1234, 1235, 1236)
foreach ($port in $ports) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $pid = $c.OwningProcess
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc -and $proc.Name -like "*mistralrs*") {
            Write-Host "停止 mistralrs (PID $pid) 监听 :$port"
            Stop-Process -Id $pid -Force
        }
    }
}
Write-Host "完成。若仍有残留，可手动 Task Manager 结束 mistralrs.exe。"
