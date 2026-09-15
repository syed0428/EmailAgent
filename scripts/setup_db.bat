@echo off
echo.
echo ============================================
echo   EmailAgent - Setup Helper
echo ============================================
echo.

set /p PGPASS=Enter your PostgreSQL password: 
set /p PGPORT=PostgreSQL port (default 5432 for PG17): 

if "%PGPORT%"=="" set PGPORT=5432

echo.
echo [1] Creating database 'emailagent' on port %PGPORT%...
set PGPASSWORD=%PGPASS%
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -p %PGPORT% -c "CREATE DATABASE emailagent;" 2>nul
if errorlevel 1 (
    echo     Database may already exist - continuing...
) else (
    echo     Database created OK.
)

echo.
echo [2] Enabling pgvector extension...
"C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -p %PGPORT% -d emailagent -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>nul
echo     Done.

echo.
echo [3] Updating .env file...
cd /d "%~dp0.."
powershell -Command "(Get-Content .env) -replace 'your_postgres_password', '%PGPASS%' -replace 'POSTGRES_PORT=5432', 'POSTGRES_PORT=%PGPORT%' | Set-Content .env"
echo     .env updated.

echo.
echo [4] Running Phase 1 verification...
cd backend
python verify.py

echo.
pause
