@echo off
echo.
echo ============================================
echo   EmailAgent - Start Backend (FastAPI)
echo ============================================
echo.
cd /d "%~dp0..\backend"
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
