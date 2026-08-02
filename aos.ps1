<#
.SYNOPSIS
    AOS 统一入口脚本 —— 不写死任何绝对路径，自动定位项目根的 .venv。
.DESCRIPTION
    2026 标准做法：用 uv 管理的 .venv 作为唯一运行环境。
    此脚本替代旧的 start.bat / run.bat / start_all.sh，消除多解释器混乱。
.EXAMPLE
    .\aos.ps1 setup     # 首次安装：创建 .venv + 装依赖
    .\aos.ps1 api       # 启动 API 服务 (:8000)
    .\aos.ps1 web       # 启动 Web 控制台 (:8501)
    .\aos.ps1 test      # 跑测试
    .\aos.ps1 shell     # 进入带环境变量的 Python REPL
    .\aos.ps1 crewai    # 验证 CrewAI + 自定义 LLM 适配器
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("setup", "api", "web", "test", "shell", "crewai", "demo", "status", "help")]
    [string]$Action = "help"
)

$ErrorActionPreference = "Stop"

# --- 自动定位项目根（脚本所在目录即为根）---
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvPip = Join-Path $ProjectRoot ".venv\Scripts\pip.exe"

# --- 统一环境变量 ---
$env:PYTHONPATH = "$ProjectRoot\src;$ProjectRoot"
$env:AOS_API_BASE = "http://127.0.0.1:8000"

# 从 .env 加载密钥（不打印值）
$EnvFile = Join-Path $ProjectRoot ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $key = $parts[0].Trim()
            $val = $parts[1].Trim()
            if (-not (Test-Path "env:$key")) {
                Set-Item -Path "env:$key" -Value $val
            }
        }
    }
}

function Ensure-Venv {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "[aos] .venv 不存在，正在用 uv 创建 (Python 3.11)..." -ForegroundColor Yellow
        uv venv --python 3.11 .venv
        if ($LASTEXITCODE -ne 0) { Write-Error "uv venv 失败"; exit 1 }
        Write-Host "[aos] 安装依赖..." -ForegroundColor Yellow
        uv pip install -e ".[dev,test]" -i https://pypi.tuna.tsinghua.edu.cn/simple
        if ($LASTEXITCODE -ne 0) { Write-Error "依赖安装失败"; exit 1 }
    }
}

function Show-Status {
    Write-Host "========== AOS 环境状态 ==========" -ForegroundColor Cyan
    Write-Host "项目根    : $ProjectRoot"
    Write-Host "Python    : $VenvPython"
    if (Test-Path $VenvPython) {
        & $VenvPython --version
        Write-Host ".venv     : OK" -ForegroundColor Green
    } else {
        Write-Host ".venv     : 不存在 (运行: .\aos.ps1 setup)" -ForegroundColor Red
    }
    Write-Host "PYTHONPATH: $env:PYTHONPATH"
    Write-Host "===================================" -ForegroundColor Cyan
}

switch ($Action) {
    "setup" {
        Write-Host "[aos] 创建/更新 .venv 并安装依赖..." -ForegroundColor Cyan
        uv venv --python 3.11 .venv
        uv pip install -e ".[dev,test]" -i https://pypi.tuna.tsinghua.edu.cn/simple
        Write-Host "[aos] 完成。运行 .\aos.ps1 status 验证。" -ForegroundColor Green
    }

    "api" {
        Ensure-Venv
        Write-Host "[aos] 启动 AOS API (:8000)..." -ForegroundColor Cyan
        Write-Host "  Docs : http://127.0.0.1:8000/docs"
        Write-Host "  Health: http://127.0.0.1:8000/health"
        & $VenvPython -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --log-level info
    }

    "web" {
        Ensure-Venv
        Write-Host "[aos] 启动 Web 控制台 (:8501)..." -ForegroundColor Cyan
        & $VenvPython -m streamlit run src/web/app.py --server.port 8501 --server.headless true --server.address 127.0.0.1 --server.baseUrlPath=/web
    }

    "test" {
        Ensure-Venv
        Write-Host "[aos] 运行测试..." -ForegroundColor Cyan
        & $VenvPython -m pytest tests/ -q --tb=short
    }

    "shell" {
        Ensure-Venv
        Write-Host "[aos] 进入 Python REPL (PYTHONPATH 已设置)..." -ForegroundColor Cyan
        & $VenvPython
    }

    "crewai" {
        Ensure-Venv
        Write-Host "[aos] 验证 CrewAI + 自定义 LLM 适配器..." -ForegroundColor Cyan
        & $VenvPython -c @"
import sys; print('Python', sys.version)
from crewai import Agent, Crew, Process, Task
from kernel.danchuang.llm import LangChainLLMAdapter, get_default_provider
p = get_default_provider()
print('Provider:', p.name())
llm = LangChainLLMAdapter(llm_provider=p, model='danchuang-llm')
agent = Agent(role='测试员', goal='验证环境', backstory='环境验证Agent', llm=llm, allow_delegation=False, verbose=False)
task = Task(description='输出一句话确认环境就绪', expected_output='一句话', agent=agent)
crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False)
r = crew.kickoff()
print('CrewAI 结果:', str(r)[:200])
print('=== CrewAI + Adapter 验证通过 ===')
"@
    }

    "demo" {
        Ensure-Venv
        Write-Host "[aos] 运行 P0 自进化闭环演示..." -ForegroundColor Cyan
        Write-Host "  默认: 真实联网(③) | AOS_REFLECT_OFF=1: 蒸馏器降级(②) | AOS_SELF_EVOLVE_LOCAL=1: 离线机制验证" -ForegroundColor Gray
        & $VenvPython examples\lifeform_self_evolve_demo.py
    }

    "status" { Show-Status }

    "help" {
        Write-Host @"
AOS 统一入口 (2026 uv 标准环境)
用法: .\aos.ps1 <action>

  setup    创建 .venv + 安装依赖 (首次必跑)
  api      启动 API 服务 (:8000)
  web      启动 Web 控制台 (:8501)
  test     运行测试
  shell    进入 Python REPL
  crewai   验证 CrewAI + LLM 适配器
  demo     运行 P0 自进化闭环演示（联网③/离线机制验证）
  status   查看环境状态
  help     显示此帮助
"@
    }
}
