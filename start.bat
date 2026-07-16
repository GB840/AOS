@echo off
chcp 65001 >nul
title AOS v1.0 — 能体操作系统
cd /d D:\AOS

set PYTHON=C:\Users\Administrator\.workbuddy\binaries\python\envs\aos\Scripts\python.exe

:menu
cls
echo ============================================
echo   AOS v1.0 — Agentic OS 物种内核
echo ============================================
echo.
echo   [1] 一键演示 (demo)
echo   [2] AI 对话 (chat)
echo   [3] 活体进化 (evolve)
echo   [4] 单元测试 (21 tests)
echo   [5] 全栈集成测试 (真LLM)
echo   [6] 启动 v5.0 API 服务 (uvicorn + Streamlit)
echo   [7] 启动 Web 控制台 (aos_server.py, 浏览器打开)
echo   [8] 系统状态 (status)
echo   [9] 列出技能 (skills)
echo   [0] 退出
echo.
set /p choice="请输入选项: "

if "%choice%"=="1" goto demo
if "%choice%"=="2" goto chat
if "%choice%"=="3" goto evolve
if "%choice%"=="4" goto test
if "%choice%"=="5" goto integration
if "%choice%"=="6" goto v5_start
if "%choice%"=="7" goto web
if "%choice%"=="8" goto status
if "%choice%"=="9" goto skills
if "%choice%"=="0" exit /b
goto menu

:demo
echo.
echo 运行综合演示...
%PYTHON% scripts\aos.py demo
pause
goto menu

:chat
echo.
set /p msg="输入问题: "
%PYTHON% scripts\aos.py chat "%msg%"
pause
goto menu

:evolve
echo.
echo 活体进化 (3 Agent, 10 任务, 真LLM驱动)...
%PYTHON% scripts\aos.py evolve --agents 3 --tasks 10 --interval 5
pause
goto menu

:test
echo.
echo 运行 21 个单元测试...
%PYTHON% -m pytest tests\test_kernel.py -v --tb=short -q
pause
goto menu

:integration
echo.
echo 全栈集成测试 (真LLM调用, 需要Zhipu key)...
%PYTHON% tests\test_integration.py
pause
goto menu

:v5_start
echo.
echo 启动 v5.0 API + UI...
start "AOS-API" cmd /c "%PYTHON% -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
timeout /t 3 /nobreak >nul
echo API: http://localhost:8000
echo Docs: http://localhost:8000/docs
echo.
echo 按任意键返回菜单 (服务在后台运行)...
pause >nul
goto menu

:status
echo.
%PYTHON% scripts\aos.py status
pause
goto menu

:web
echo.
echo 启动 Web 控制台...
echo 浏览器打开 http://localhost:8000
start http://localhost:8000
rem %PYTHON% aos_server.py
goto menu

:skills
echo.
%PYTHON% scripts\aos.py skills
pause
goto menu
