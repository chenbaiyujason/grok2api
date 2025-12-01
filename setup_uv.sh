#!/bin/bash
# UV 环境设置脚本

# 安装 uv（如果未安装）
if ! command -v uv &> /dev/null; then
    echo "正在安装 uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# 创建虚拟环境
echo "创建虚拟环境..."
uv venv

# 激活虚拟环境
echo "激活虚拟环境..."
source .venv/bin/activate

# 安装依赖
echo "安装依赖..."
uv pip install -r requirements.txt

echo "环境设置完成！"
echo "使用以下命令激活环境："
echo "  source .venv/bin/activate"
echo "或"
echo "  uv run python main.py"

