# AOS Layer 1 traffic-split telemetry probe (run on Windows host at D:\AOS, NOT sandbox)
# Purpose: turn "what is the real split %" into real numbers, verify AOS_KERNEL_TRAFFIC_PCT.
#
# Prereqs:
#   1) deps installed (pip install -e . or equivalent)
#   2) single worker start so telemetry counters are not sharded across processes
#   3) kernel path needs a usable model backend (bridge.chat -> AOSKernel -> ModelGateway).
#      Even if backend is down, this script still verifies the "split decision"
#      via kernel_split_ratio; backend health is seen via chat_kernel_ok / chat_kernel_fail.
param(
    [int]$Pct = 50,
    [int]$Requests = 40,
    [int]$Port = 8000,
    [int]$MountTimeout = 40
)
$ErrorActionPreference = "Stop"
$ROOT = "D:\AOS"
New-Item -ItemType Directory -Force -Path "$ROOT\logs" | Out-Null

# Auto-locate python (host system Python 3.14 usually at the path below)
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" }
$ENV:PYTHONPATH = "$ROOT\src"
$ENV:AOS_KERNEL_TRAFFIC_PCT = "$Pct"

# [1] start API (single worker, background)
Write-Host "[1/4] Starting API server (single worker, AOS_KERNEL_TRAFFIC_PCT=$Pct) ..."
$proc = Start-Process -FilePath $Py -ArgumentList @(
    "-m","uvicorn","src.api.main:app","--host","0.0.0.0","--port","$Port","--workers","1"
) -WorkingDirectory $ROOT -RedirectStandardOutput "$ROOT\logs\aos_api.out" -RedirectStandardError "$ROOT\logs\aos_api.err" -PassThru

# [2] wait for bridge mount (mount_success=1)
Write-Host "[2/4] Waiting for bridge mount (up to $MountTimeout sec) ..."
$mounted = $false
for ($s=0; $s -lt $MountTimeout; $s++) {
    try {
        $h = curl.exe -s "http://localhost:$Port/api/v1/health" | & $Py -c "import sys,json;d=json.load(sys.stdin);t=d.get('telemetry',{});print(str(t.get('mount_success'))+' '+str(t.get('last_mount_error')))" 2>$null
        if ($h -like "1 *") { $mounted=$true; Write-Host "  bridge mounted"; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $mounted) {
    Write-Host "  !! bridge not mounted within timeout, see logs\aos_api.err"
    Write-Host (Get-Content "$ROOT\logs\aos_api.err" -Tail 15)
    Stop-Process -Id $proc.Id -Force; exit 1
}

# [3] drive traffic
Write-Host "[3/4] Driving $Requests /api/chat requests ..."
for ($i=1; $i -le $Requests; $i++) {
    curl.exe -s -X POST "http://localhost:$Port/api/chat" -H "Content-Type: application/json" -d '{"message":"hello"}' > $null
}

# [4] read telemetry snapshot + verdict
Write-Host "[4/4] /api/v1/health telemetry:"
curl.exe -s "http://localhost:$Port/api/v1/health" | & $Py -c @'
import sys, json
d = json.load(sys.stdin)
t = d.get('telemetry', {})
def g(k): return t.get(k)
rt = g('chat_request_total') or 0
rk = g('chat_route_kernel') or 0
print('  mount_success      =', g('mount_success'))
print('  chat_request_total =', rt, ' (total requests)')
print('  chat_route_kernel  =', rk, ' (routed to kernel)')
print('  chat_route_brain   =', g('chat_route_brain'), ' (routed to brain)')
print('  kernel_split_ratio =', g('kernel_split_ratio'), ' (REAL split ratio)')
print('  chat_kernel_ok     =', g('chat_kernel_ok'))
print('  chat_kernel_fail   =', g('chat_kernel_fail'))
print('  chat_kernel_ratio  =', g('chat_kernel_ratio'), ' (kernel health ok/(ok+fail))')
print()
if rt == 0:
    print('  [VERDICT] No request counted: bridge not mounted or /api/chat not reached')
elif rk == 0 and not g('chat_kernel_fail'):
    print('  [VERDICT] Split NOT active: kernel route not triggered (check AOS_KERNEL_TRAFFIC_PCT / bridge mount)')
elif rk > 0 and not g('chat_kernel_fail'):
    print('  [VERDICT] Split active AND kernel healthy: kernel_split_ratio should approx = AOS_KERNEL_TRAFFIC_PCT')
elif rk > 0 and g('chat_kernel_fail'):
    print('  [VERDICT] Split decision active (routed to kernel) BUT kernel backend FAILED: chat_kernel_fail>0, fix model backend first')
'@

Write-Host "`nStopping server ..."
Stop-Process -Id $proc.Id -Force
