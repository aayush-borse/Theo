@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title THEO - Multimodal Annotation & Quality Platform
if not exist ".venv\Scripts\python.exe" (
  echo [THEO] Creating Python environment...
  py -3.11 -m venv .venv 2>nul
  if errorlevel 1 py -3.10 -m venv .venv
  if errorlevel 1 (echo Install Python 3.10 or 3.11+ and enable PATH.& pause & exit /b 1)
)
if not exist ".env" copy .env.example .env >nul
findstr /B /C:"THEO_JWT_SECRET=replace-with" .env >nul
if not errorlevel 1 (
  for /f %%i in ('".venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"') do set THEO_SECRET=%%i
  powershell -NoProfile -Command "$p='.env'; $s=Get-Content $p -Raw; $s=$s -replace 'THEO_JWT_SECRET=replace-with-a-random-secret-at-least-32-characters', 'THEO_JWT_SECRET=%THEO_SECRET%'; Set-Content -Path $p -Value $s -NoNewline"
)
echo [THEO] Installing backend dependencies (first launch may take a few minutes)...
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r backend\requirements.txt
if errorlevel 1 (echo Dependency installation failed. Check internet access.& pause & exit /b 1)
echo [THEO] Starting local application at http://127.0.0.1:8000
start "THEO" http://127.0.0.1:8000
set PYTHONPATH=%CD%\backend
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
pause
