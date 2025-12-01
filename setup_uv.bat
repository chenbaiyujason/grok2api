@echo off
REM UV 环境设置脚本 (Windows)

REM 检查 uv 是否已安装
where uv >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo 正在安装 uv...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set PATH=%USERPROFILE%\.cargo\bin;%PATH%
)

REM 创建虚拟环境
echo 创建虚拟环境...
uv venv

REM 激活虚拟环境
echo 激活虚拟环境...
call .venv\Scripts\activate.bat

REM 安装依赖
echo 安装依赖...
uv pip install -r requirements.txt

echo 环境设置完成！
echo 使用以下命令激活环境：
echo   .venv\Scripts\activate.bat
echo 或
echo   uv run python main.py

pause

