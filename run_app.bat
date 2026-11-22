@echo off
setlocal

REM Always run from repository root (folder of this script)
cd /d "%~dp0"

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm is not installed or not in PATH.
  echo Install Node.js from https://nodejs.org and try again.
  exit /b 1
)

echo Starting full local stack (Ollama + API + UI)...
npm run run:local
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Application exited with code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
