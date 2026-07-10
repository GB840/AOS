# 用真实 mistralrs.exe `serve` 子命令拉起三个本地模型，对接 AOS LLM 路由。
# 串行启动：等当前模型 ISQ 量化完、端口就绪后，再起下一个，避免 F16->Q4 量化瞬时
# 内存峰值叠加导致 OOM（本机 8GB 无 GPU，三个模型量化中峰值约 5~6GB）。
$exe = "C:\Users\Administrator\.mistralrs\mistralrs.exe"
$log = "D:\AOS\logs\mistralrs"
New-Item -ItemType Directory -Force -Path $log | Out-Null

function Wait-Port($port, $timeoutSec = 600) {
    $end = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $end) {
        try {
            $c = New-Object System.Net.Sockets.TcpClient
            $c.Connect("127.0.0.1", $port); $c.Close()
            return $true
        } catch { Start-Sleep -Seconds 5 }
    }
    return $false
}

# 1) MiniCPM5-1B (GENERAL / 全能) — 已是 GGUF Q4，直接 mmap 加载，最快
Write-Host "[1/3] 启动 MiniCPM5 -> :1234 (GENERAL)"
Start-Process -FilePath $exe -ArgumentList @("serve","-m","C:\Users\Administrator\MiniCPM5-1B-GGUF","--format","gguf","-f","MiniCPM5-1B-Q4_K_M.gguf","-p","1234","--no-ui") `
    -RedirectStandardOutput "$log\minicpm_serve.log" -RedirectStandardError "$log\minicpm_serve.err" -NoNewWindow
if (-not (Wait-Port 1234)) { Write-Warning "MiniCPM 启动超时，详见 $log\minicpm_serve.err" ; exit 1 }
Write-Host "      MiniCPM5 就绪 :1234"

# 2) Qwen2.5-Coder-3B (CODING / 写代码) — F16 + 就地 ISQ Q4K
Write-Host "[2/3] 启动 Qwen2.5-Coder -> :1235 (CODING)  [ISQ 量化中，CPU 约数分钟]"
Start-Process -FilePath $exe -ArgumentList @("serve","-m","D:\models\Qwen2.5-Coder-3B-Instruct","--isq","Q4K","-p","1235","--no-ui") `
    -RedirectStandardOutput "$log\qwen_serve.log" -RedirectStandardError "$log\qwen_serve.err" -NoNewWindow
if (-not (Wait-Port 1235)) { Write-Warning "Qwen 启动超时，详见 $log\qwen_serve.err" ; exit 1 }
Write-Host "      Qwen2.5-Coder 就绪 :1235"

# 3) DeepSeek-R1-Distill-Qwen-1.5B (REASONING / 推理) — F16 + 就地 ISQ Q4K
Write-Host "[3/3] 启动 DeepSeek-R1-1.5B -> :1236 (REASONING)  [ISQ 量化中]"
Start-Process -FilePath $exe -ArgumentList @("serve","-m","D:\models\DeepSeek-R1-1.5B","--isq","Q4K","-p","1236","--no-ui") `
    -RedirectStandardOutput "$log\deepseek_serve.log" -RedirectStandardError "$log\deepseek_serve.err" -NoNewWindow
if (-not (Wait-Port 1236)) { Write-Warning "DeepSeek 启动超时，详见 $log\deepseek_serve.err" ; exit 1 }
Write-Host "      DeepSeek-R1-1.5B 就绪 :1236"

Write-Host ""
Write-Host "全部就绪："
Write-Host "  GENERAL   -> http://localhost:1234/v1  (MiniCPM5-1B)"
Write-Host "  CODING    -> http://localhost:1235/v1  (Qwen2.5-Coder-3B)"
Write-Host "  REASONING -> http://localhost:1236/v1  (DeepSeek-R1-1.5B)"
