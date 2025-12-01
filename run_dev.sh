#!/bin/bash
# 开发环境启动脚本

# 激活虚拟环境
source .venv/bin/activate

# 启动服务（带热重载）
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

