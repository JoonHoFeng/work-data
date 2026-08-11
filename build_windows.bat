@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   工作日志 - Windows 打包 (PyInstaller)
echo ========================================
echo.
echo 请在 Windows 上运行本脚本。输出: dist\Worklog\Worklog.exe
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.9+ 并勾选 Add to PATH
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] 创建虚拟环境...
  python -m venv .venv
)

echo [2/4] 安装依赖...
call .venv\Scripts\activate.bat
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
pip install -q "pyinstaller>=6.0"

echo [3/4] 打 Streamlit 中文菜单补丁...
python scripts\patch_streamlit_zh.py

echo [4/4] PyInstaller 打包（可能需要几分钟）...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
pyinstaller --noconfirm worklog.spec
if errorlevel 1 (
  echo.
  echo [失败] 打包出错，请把上方报错发出来排查
  pause
  exit /b 1
)

echo.
echo ========================================
echo   完成！
echo   双击运行: dist\Worklog\Worklog.exe
echo   可将整个 dist\Worklog 文件夹拷到任意 Windows 电脑使用
echo   数据库会写在 exe 同目录的 data\ 下
echo ========================================
explorer dist\Worklog
pause
