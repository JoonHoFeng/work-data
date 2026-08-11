@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Stopping Worklog...

REM Stop packaged exe
taskkill /F /IM Worklog.exe >nul 2>nul
if not errorlevel 1 echo Stopped Worklog.exe

REM Stop streamlit / python processes started for this app
REM (best-effort: kill streamlit run app.py)
for /f "tokens=2 delims=," %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO CSV /NH 2^>nul') do (
  wmic process where "ProcessId=%%~i" get CommandLine 2>nul | findstr /I "streamlit run app.py" >nul
  if not errorlevel 1 (
    taskkill /F /PID %%~i >nul 2>nul
  )
)

REM Broader fallback (may stop other streamlit apps on this machine)
taskkill /F /IM streamlit.exe >nul 2>nul

if exist streamlit.pid (
  for /f %%p in (streamlit.pid) do taskkill /F /PID %%p >nul 2>nul
  del /f /q streamlit.pid >nul 2>nul
)

echo Done. If browser still open, just close the tab.
endlocal
