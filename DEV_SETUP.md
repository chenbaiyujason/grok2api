# 本地开发环境设置

## 使用 UV 管理环境

### Windows

1. **安装 UV**（如果未安装）：
   ```powershell
   powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **设置环境**：
   ```cmd
   setup_uv.bat
   ```

3. **激活环境并启动**：
   ```cmd
   .venv\Scripts\activate.bat
   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

   或直接使用：
   ```cmd
   uv run uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

### Linux/Mac

1. **安装 UV**（如果未安装）：
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **设置环境**：
   ```bash
   chmod +x setup_uv.sh
   ./setup_uv.sh
   ```

3. **激活环境并启动**：
   ```bash
   source .venv/bin/activate
   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

   或直接使用：
   ```bash
   uv run uvicorn main:app --host 0.0.0.0 --port 8001 --reload
   ```

## VSCode 调试

### 配置说明

项目已包含 VSCode 调试配置（`.vscode/launch.json`），提供两种调试方式：

1. **Python: Flow2API** - 直接运行 main.py
2. **Python: Flow2API (uvicorn)** - 使用 uvicorn 模块运行（支持热重载）

### 使用方法

1. 按 `F5` 或点击调试按钮
2. 选择配置（推荐使用 "Python: Flow2API (uvicorn)"）
3. 开始调试

### 环境变量

调试配置中已设置：
- `PYTHONPATH`: 项目根目录
- `STORAGE_MODE`: file（文件存储模式）

如需修改，编辑 `.vscode/launch.json` 中的 `env` 部分。

## 快速启动脚本

### Windows
```cmd
run_dev.bat
```

### Linux/Mac
```bash
chmod +x run_dev.sh
./run_dev.sh
```

## 注意事项

- 确保已安装 Python 3.8+
- 首次运行前需要先执行 `setup_uv.sh` 或 `setup_uv.bat` 安装依赖
- 虚拟环境位于 `.venv` 目录
- 配置文件位于 `data/setting.toml`

