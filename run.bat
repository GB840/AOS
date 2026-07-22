@echo off
chcp 65001 >nul
title AOS v5.0
cd /d D:\AOS

set PYTHON=C:\Users\Administrator\AppData\Local\Programs\Python\Python314\python.exe
set PYTHONPATH=D:\AOS\src;D:\AOS
set AOS_API_BASE=http://127.0.0.1:8000

echo.
echo   ========================================
echo     AOS v5.0 - Starting...
echo   ========================================
echo.
echo   API : http://localhost:8000
echo   Web : http://localhost:8000/web/   (完整控制台)
echo   Docs: http://localhost:8000/docs
echo   Health: http://localhost:8000/health
echo.
echo   Press Ctrl+C to stop.
echo   ----------------------------------------
echo.

if not exist "%PYTHON%" (
    echo   [ERROR] Python not found: %PYTHON%
    echo   Please edit line 7 of this file.
    pause
    exit /b 1
)

REM 1) 启动 API (后台)
echo [run.bat] 启动 AOS API (:8000)...
start "AOS API" "%PYTHON%" -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --log-level info

REM 等待 API 健康
set /a tries=0
:waitapi
curl -s -m 4 -o nul http://127.0.0.1:8000/health >nul 2>nul
if not errorlevel 1 goto apiup
set /a tries+=1
if %tries% lss 40 (timeout /t 3 >nul & goto waitapi)
:apiup
echo [run.bat] API 就绪.

REM 2) 启动 Web 控制台 (Streamlit :8501 -> /web/)
"%PYTHON%" -c "import streamlit" >nul 2>nul
if errorlevel 1 (
  echo [run.bat] 警告: 当前 Python 未安装 streamlit，Web 控制台无法启动。
  echo           请用完整启动: bash start_all.sh  (aos venv 含 streamlit)
) else (
  echo [run.bat] 启动 Web 控制台 (:8501 -> /web/)...
  start "AOS Web" "%PYTHON%" -m streamlit run src/web/app.py --server.port 8501 --server.headless true --server.address 127.0.0.1 --server.baseUrlPath=/web
)

echo.
echo   全部就绪。浏览器打开: http://127.0.0.1:8000/web/
echo   左侧点 "🚀 自主执行"，一句话/语音触发，看完整过程。
echo   (停止: 关闭 "AOS API" 与 "AOS Web" 两个窗口)
echo.
pause
