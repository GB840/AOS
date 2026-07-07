@echo off
chcp 65001 >nul
title AOS v5.0 - 能体操作系统

echo ============================================
echo   AOS v5.0 - Agent Operating System
echo   Hermes v0.15.2 + DeerFlow 2.0 DEEP
echo ============================================
echo.

cd /d D:\AOS

echo [1/2] Starting API server...
start "AOS-API" cmd /c "python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Streamlit UI...
start "AOS-UI" cmd /c "streamlit run src/web/app.py --server.port 8501"

echo.
echo ============================================
echo   AOS is running!
echo   API:  http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo   UI:   http://localhost:8501
echo ============================================
echo.
echo Press any key to stop all services...
pause >nul

taskkill /FI "WINDOWTITLE eq AOS-API*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AOS-UI*" /T /F >nul 2>&1
echo AOS stopped.
