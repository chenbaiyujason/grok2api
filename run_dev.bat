@echo off
REM 开发环境启动脚本 (Windows)

REM 激活虚拟环境
call .venv\Scripts\activate.bat

REM 启动服务（带热重载）
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

pause

