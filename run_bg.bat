@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM Background start for development (source code)
REM Usage: double-click run_bg.bat   or   run_bg.bat

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: python not found in PATH.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv and installing deps...
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)

if not exist "data\worklog.db" (
  ".venv\Scripts\python.exe" scripts\init_db.py
)

set PORT=8501
if not "%WORKLOG_PORT%"=="" set PORT=%WORKLOG_PORT%

echo Starting Worklog in background on http://127.0.0.1:%PORT%
echo Log: streamlit.log
echo Stop: stop.bat

REM hidden console via VBScript helper
cscript //nologo "%~dp0run_bg.vbs" "%~dp0" "%PORT%"
if errorlevel 1 (
  echo Fallback: start minimized window...
  start "Worklog" /MIN ".venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port %PORT% --server.address 127.0.0.1
)

timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%PORT%"
echo Done.
endlocal
