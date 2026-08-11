@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo   Worklog - Windows build (PyInstaller)
echo ========================================
echo.
echo Output: dist\Worklog\Worklog.exe
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found.
  echo Install Python 3.9+ from https://www.python.org/downloads/
  echo Check "Add python.exe to PATH" during install.
  echo.
  pause
  exit /b 1
)

echo [1/4] Python found:
python --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [2/4] Creating venv...
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create venv.
    pause
    exit /b 1
  )
) else (
  echo [2/4] venv already exists.
)

echo.
echo [3/4] Installing dependencies...
call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate venv.
  pause
  exit /b 1
)

python -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] pip upgrade failed.
  pause
  exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] pip install requirements failed.
  pause
  exit /b 1
)

python -m pip install "pyinstaller>=6.0"
if errorlevel 1 (
  echo [ERROR] pip install pyinstaller failed.
  pause
  exit /b 1
)

echo.
echo [3b] Optional Streamlit Chinese menu patch...
if exist "scripts\patch_streamlit_zh.py" (
  python scripts\patch_streamlit_zh.py
)

echo.
echo [4/4] Building with PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller --noconfirm worklog.spec
if errorlevel 1 (
  echo.
  echo [ERROR] PyInstaller build failed. See messages above.
  pause
  exit /b 1
)

if not exist "dist\Worklog\Worklog.exe" (
  echo [ERROR] dist\Worklog\Worklog.exe was not created.
  pause
  exit /b 1
)

REM copy background helper next to exe
if exist "run_exe_bg.vbs" copy /Y "run_exe_bg.vbs" "dist\Worklog\run_exe_bg.vbs" >nul
if exist "stop.bat" copy /Y "stop.bat" "dist\Worklog\stop.bat" >nul

echo.
echo ========================================
echo   BUILD OK
echo   Run: dist\Worklog\Worklog.exe
echo   Background: dist\Worklog\run_exe_bg.vbs
echo   Stop: dist\Worklog\stop.bat
echo   Copy the whole folder: dist\Worklog
echo   DB path: next to exe, data\worklog.db
echo ========================================
echo.

if exist "dist\Worklog" explorer "dist\Worklog"
pause
endlocal
