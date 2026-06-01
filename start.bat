@echo off
setlocal EnableExtensions

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv was not found.
  echo Run install.bat first.
  exit /b 1
)

set PYTHONPATH=%CD%\src;%PYTHONPATH%

echo Starting Instant Easy Rename...
echo.
echo Health: http://127.0.0.1:17891/health
echo Jobs:   http://127.0.0.1:17891/jobs
echo.
echo The UI window should open shortly.
echo Keep this window open while testing. Close the UI or press Ctrl+C to stop.
echo.

".venv\Scripts\python.exe" -m instant_easy_rename_server --ui
