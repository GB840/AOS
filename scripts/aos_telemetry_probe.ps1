# AOS Layer 1 切流遥测实测（在 Windows 主机 D:\AOS 下运行，非沙箱）
# 作用：把「切流 % 是测量缺口」变成真实数字，验证 AOS_KERNEL_TRAFFIC_PCT 真实生效。
#
# 前置：
#   1) 依赖已装（pip install -e . 或同等）
#   2) 用单 worker 启动，保证 telemetry 计数器不被多进程分片
#   3) 内核链路需要可用模型后端（bridge.chat -> AOSKernel -> ModelGateway）。
#      即便后端未就绪，本脚本也能验证「切流决策」是否生效
#      （看 kernel_split_ratio）；后端成败另看 chat_kernel_ok / chat_kernel_fail。
param(
    [int]$Pct = 50,           # 切流比例：发往内核的 %；默认 50 以便清晰看到分流
    [int]$Requests = 40,      # 驱动流量次数
    [int]$Port = 8000,
    [int]$MountTimeout = 40   # 等待 bridge 挂载的秒数
)
$ErrorActionPreference = "Stop"
$ROOT = "D:\AOS"
New-Item -ItemType Directory -Force -Path "$ROOT\logs" | Out-Null

# 自动定位 python（主机系统 Python 3.14 通常在下述路径）
$Py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Py) { $Py = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe" }
$ENV:PYTHONPATH = "$ROOT\src"
$ENV:AOS_KERNEL_TRAFFIC_PCT = "$Pct"

# ── 1) 启动 API（单 worker，后台）──
Write-Host "[1/4] 启动 API server (单 worker, AOS_KERNEL_TRAFFIC_PCT=$Pct) ..."
$proc = Start-Process -FilePath $Py -ArgumentList @(
    "-m","uvicorn","src.api.main:app","--host","0.0.0.0","--port","$Port","--workers","1"
) -WorkingDirectory $ROOT -RedirectStandardOutput "$ROOT\logs\aos_api.out" -RedirectStandardError "$ROOT\logs\aos_api.err" -PassThru

# ── 2) 等待 bridge 挂载（mount_success=1）──
Write-Host "[2/4] 等待 bridge 挂载 (最多 $MountTimeout 秒) ..."
$mounted = $false
for ($s=0; $s -lt $MountTimeout; $s++) {
    try {
        $h = curl.exe -s "http://localhost:$Port/api/v1/health" | & $Py -c "import sys,json;d=json.load(sys.stdin);t=d.get('telemetry',{});print(str(t.get('mount_success'))+' '+str(t.get('last_mount_error')))" 2>$null
        if ($h -like "1 *") { $mounted=$true; Write-Host "  bridge 已挂载"; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $mounted) {
    Write-Host "  !! bridge 未在超时内挂载，详见 logs\aos_api.err"
    Write-Host (Get-Content "$ROOT\logs\aos_api.err" -Tail 15)
    Stop-Process -Id $proc.Id -Force; exit 1
}

# ── 3) 驱动流量 ──
Write-Host "[3/4] 驱动 $Requests 次 /api/chat ..."
for ($i=1; $i -le $Requests; $i++) {
    curl.exe -s -X POST "http://localhost:$Port/api/chat" -H "Content-Type: application/json" -d '{"message":"你好，介绍一下你自己"}' > $null
}

# ── 4) 读取遥测快照 + 解释 ──
Write-Host "[4/4] /api/v1/health telemetry："
curl.exe -s "http://localhost:$Port/api/v1/health" | & $Py -c @'
import sys, json
d = json.load(sys.stdin)
t = d.get('telemetry', {})
def g(k): return t.get(k)
rt = g('chat_request_total') or 0
rk = g('chat_route_kernel') or 0
print('  mount_success      =', g('mount_success'))
print('  chat_request_total =', rt, ' (总请求数)')
print('  chat_route_kernel  =', rk, ' (发往内核的决策数)')
print('  chat_route_brain   =', g('chat_route_brain'), ' (发往 brain 的决策数)')
print('  kernel_split_ratio =', g('kernel_split_ratio'), ' (发往内核比例 = 切流真实值)')
print('  chat_kernel_ok     =', g('chat_kernel_ok'))
print('  chat_kernel_fail   =', g('chat_kernel_fail'))
print('  chat_kernel_ratio  =', g('chat_kernel_ratio'), ' (内核健康度 ok/(ok+fail))')
print()
if rt == 0:
    print('  [结论] 无请求计数: bridge 未挂载或 /api/chat 未到达计数点')
elif rk == 0 and not g('chat_kernel_fail'):
    print('  [结论] 切流未生效: 内核路由未被触发 (检查 AOS_KERNEL_TRAFFIC_PCT / bridge 挂载)')
elif rk > 0 and not g('chat_kernel_fail'):
    print('  [结论] 切流生效且内核健康: kernel_split_ratio 应约= AOS_KERNEL_TRAFFIC_PCT')
elif rk > 0 and g('chat_kernel_fail'):
    print('  [结论] 切流决策生效(发往内核), 但内核后端失败: chat_kernel_fail>0 需先修模型后端')
'@

Write-Host "`n停止 server ..."
Stop-Process -Id $proc.Id -Force
