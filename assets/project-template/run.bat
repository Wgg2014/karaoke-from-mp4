@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo 未找到 Python。请安装 Python 3.12，并勾选 Add Python to PATH。
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 正在创建虚拟环境并安装依赖……
  python -m venv .venv
  if errorlevel 1 goto :failed
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :failed
)

if "%~1"=="" (
  ".venv\Scripts\python.exe" main.py
) else if "%~2"=="" (
  echo 请同时选择视频和字幕，再一起拖到 run.bat。
  pause
  exit /b 2
) else (
  ".venv\Scripts\python.exe" main.py "%~1" "%~2"
)
if errorlevel 1 goto :failed

echo.
echo 处理完成，文件位于 output 目录。
pause
exit /b 0

:failed
echo.
echo 处理失败，请查看 output\处理日志.log。
pause
exit /b 1
