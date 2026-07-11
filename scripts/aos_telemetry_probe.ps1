# AOS Layer 1 切流遥测实测配方（在 Windows 主机 D:\AOS 下运行，非沙箱）
# 作用：把「切流 % 是测量缺口」变成真实数字。
#
# 前置：
#   1) 依赖已装（make install / pip install -e .）
#   2) 模型后端可用：内核链路 bridge.chat() -> AOSKernel.send_message -> ModelGateway
#      (mistralrs -> litellm -> cloud)。至少需要一个可用后端，否则 chat_kernel_fail 会涨、
#      chat_kernel_ratio 会掉。这是「真数字」能否出来的关键外部条件。
#   3) 用单 worker 启动，保证 telemetry 计数器不被多进程分片。

$ErrorActionPreference = "Stop"
$ROOT = "D:\AOS"
$ENV:PYTHONPATH = "$ROOT\src"

# ── 1) 启动 API（单 worker，后台）──
Write-Host "[1/4] 启动 API server (单 worker) ..."
$proc = Start-Process -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "src.api.main:app",
    "--host", "0.0.0.0", "--port", "8000", "--workers", "1"
) -WorkingDirectory $ROOT -RedirectStandardOutput "$ROOT\logs\aos_api.out" -RedirectStandardError "$ROOT\logs\aos_api.err" -PassThru
Start-Sleep -Seconds 8

# ── 2) 验证 bridge 挂载成功 ──
Write-Host "[2/4] 检查 bridge 挂载 ..."
$mount = curl.exe -s http://localhost:8000/api/v1/health | python -c "import sys,json;d=json.load(sys.stdin);print('mount_success=',d.get('telemetry',{}).get('mount_success'),'last_err=',d.get('telemetry',{}).get('last_mount_error'))"
Write-Host $mount

# ── 3) 驱动流量：默认 AOS_KERNEL_TRAFFIC_PCT=100 -> /api/chat 全走内核 ──
Write-Host "[3/4] 驱动 30 次 /api/chat ..."
for ($i=1; $i -le 30; $i++) {
    curl.exe -s -X POST http://localhost:8000/api/chat `
        -H "Content-Type: application/json" `
        -d '{"message":"你好，介绍一下你自己"}' > $null
}

# ── 4) 读取遥测快照 ──
Write-Host "[4/4] 读取 /api/v1/health 的 telemetry："
curl.exe -s http://localhost:8000/api/v1/health | python -c @"
import sys, json
d = json.load(sys.stdin)
t = d.get('telemetry', {})
print('  chat_total        =', t.get('chat_total'))
print('  chat_kernel_ok    =', t.get('chat_kernel_ok'))
print('  chat_kernel_fail  =', t.get('chat_kernel_fail'))
print('  chat_kernel_ratio =', t.get('chat_kernel_ratio'))
print('  mount_attempts    =', t.get('mount_attempts'))
print('  mount_success     =', t.get('mount_success'))
print('  last_mount_error  =', t.get('last_mount_error'))
"@

Write-Host "`n读数说明："
Write-Host "  - chat_kernel_ratio 接近 1.0 => 内核路径真实可用，切流生效"
Write-Host "  - chat_kernel_fail > 0      => 模型后端未就绪或内核链路报错，需先修后端"
Write-Host "  - 想看分流效果：重启时设 AOS_KERNEL_TRAFFIC_PCT=50，再看 ratio 约为命中内核的比例"
Write-Host "  - 注意：当前 telemetry 只统计「走内核」的调用，brain 回退部分不计入，"
Write-Host "    所以 pct<100 时 chat_total 会小于真实请求数（已知测量缺口，待补总计数器）"

# 停止 server
Write-Host "`n停止 server ..."
Stop-Process -Id $proc.Id -Force
