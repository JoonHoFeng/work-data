@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo  Worklog Windows build
echo ========================================

where python >nul 2>nul
if errorlevel 1 goto NO_PYTHON

python --version
echo.

if not exist ".venv\Scripts\python.exe" (
  echo Creating venv...
  python -m venv .venv
  if errorlevel 1 goto FAIL
)

echo Installing packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto FAIL
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto FAIL
".venv\Scripts\python.exe" -m pip install "pyinstaller>=6.0"
if errorlevel 1 goto FAIL

if exist "scripts\patch_streamlit_zh.py" (
  ".venv\Scripts\python.exe" scripts\patch_streamlit_zh.py
)

echo Building...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
".venv\Scripts\python.exe" -m PyInstaller --noconfirm worklog.spec
if errorlevel 1 goto FAIL

if not exist "dist\Worklog\Worklog.exe" goto FAIL

echo.
echo BUILD OK
echo Run: dist\Worklog\Worklog.exe
echo Copy whole folder: dist\Worklog
echo.
if exist "dist\Worklog" explorer "dist\Worklog"
pause
exit /b 0

:NO_PYTHON
echo ERROR: python not found in PATH.
echo Install Python 3.9+ and enable Add to PATH.
pause
exit /b 1

:FAIL
echo ERROR: build failed. Read messages above.
pause
exit /b 1
