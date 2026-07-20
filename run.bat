@echo off
chcp 65001 >nul
title AOS — 一键启动
cd /d D:\AOS

:: ═══════════════════════════════════════════════════════════
::  AOS 一键启动（8G 内存友好：只起核心 API，不拉全家桶）
::  双击即跑，Ctrl+C 停止
:: ═══════════════════════════════════════════════════════════

set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe
set PYTHONPATH=D:\AOS\src;D:\AOS

echo.
echo   ╔══════════════════════════════════════╗
echo   ║   AOS v5.0 — 一键启动              ║
echo   ╚══════════════════════════════════════╝
echo.
echo   [核心] API 服务  → http://localhost:8000
echo   [文档] Swagger   → http://localhost:8000/docs
echo   [健康] 心跳检测  → http://localhost:8000/health
echo.
echo   按 Ctrl+C 停止服务
echo   ─────────────────────────────────────────
echo.

:: 检查 Python 是否存在
if not exist "%PYTHON%" (
    echo   [错误] 找不到 Python: %PYTHON%
    echo   请修改本文件第 12 行的 PYTHON 路径
    pause
    exit /b 1
)

:: 启动 API（单进程，8G 内存足够）
"%PYTHON%" -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --log-level info

:: 如果 uvicorn 崩了，暂停让用户看到错误
pause
