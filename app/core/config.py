"""配置管理器 - 管理应用配置的读写"""

import toml
from pathlib import Path
from typing import Dict, Any, Optional, Literal

from app.core.env import env


# 默认配置
DEFAULT_FLOW = {
    "session_token": "",
    "csrf_token": ""
}

DEFAULT_GLOBAL = {
    "base_url": "http://localhost:8000",
    "log_level": "INFO",
    "admin_password": "admin",
    "admin_username": "admin"
}


class ConfigManager:
    """配置管理器"""

    def __init__(self) -> None:
        """初始化配置"""
        self.config_path: Path = Path(__file__).parents[2] / "data" / "setting.toml"
        self._storage: Optional[Any] = None
        self._ensure_exists()
        self.global_config: Dict[str, Any] = self.load("global")
        self.flow_config: Dict[str, Any] = self.load("flow")
    
    def _ensure_exists(self) -> None:
        """确保配置存在"""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self._create_default()
    
    def _create_default(self) -> None:
        """创建默认配置"""
        default = {"flow": DEFAULT_FLOW.copy(), "global": DEFAULT_GLOBAL.copy()}
        with open(self.config_path, "w", encoding="utf-8") as f:
            toml.dump(default, f)
    
    def _normalize_proxy(self, proxy: str) -> str:
        """标准化代理URL（socks5:// → socks5h://）"""
        if proxy and proxy.startswith("socks5://"):
            return proxy.replace("socks5://", "socks5h://", 1)
        return proxy
    
    def _normalize_cf(self, cf: str) -> str:
        """标准化CF Clearance（自动添加前缀）"""
        if cf and not cf.startswith("cf_clearance="):
            return f"cf_clearance={cf}"
        return cf

    def set_storage(self, storage: Any) -> None:
        """设置存储实例"""
        self._storage = storage

    def load(self, section: Literal["global", "flow"]) -> Dict[str, Any]:
        """加载配置节"""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = toml.load(f)
            
            # 如果配置节不存在，使用默认值并更新配置文件
            if section not in config:
                default_config = DEFAULT_FLOW.copy() if section == "flow" else DEFAULT_GLOBAL.copy()
                config[section] = default_config
                # 保存更新后的配置
                with open(self.config_path, "w", encoding="utf-8") as f:
                    toml.dump(config, f)
                return default_config
            
            return config[section]
        except Exception as e:
            raise Exception(f"[Setting] 配置加载失败: {e}") from e
    
    async def reload(self) -> None:
        """重新加载配置"""
        self.global_config = self.load("global")
        self.flow_config = self.load("flow")
    
    async def _save_file(self, updates: Dict[str, Dict[str, Any]]) -> None:
        """保存到文件"""
        import aiofiles
        
        async with aiofiles.open(self.config_path, "r", encoding="utf-8") as f:
            config = toml.loads(await f.read())
        
        for section, data in updates.items():
            if section in config:
                config[section].update(data)
        
        async with aiofiles.open(self.config_path, "w", encoding="utf-8") as f:
            await f.write(toml.dumps(config))
    
    async def _save_storage(self, updates: Dict[str, Dict[str, Any]]) -> None:
        """保存到存储"""
        config = await self._storage.load_config()
        
        for section, data in updates.items():
            if section in config:
                config[section].update(data)
        
        await self._storage.save_config(config)
    
    async def save(self, global_config: Optional[Dict[str, Any]] = None, flow_config: Optional[Dict[str, Any]] = None) -> None:
        """保存配置"""
        updates = {}
        
        if global_config:
            updates["global"] = global_config
        if flow_config:
            updates["flow"] = flow_config
        
        # 选择存储方式
        if self._storage:
            await self._save_storage(updates)
        else:
            await self._save_file(updates)
        
        await self.reload()
    
    def get_session_token(self) -> str:
        """获取 session_token，优先使用管理后台配置，如果没有则使用环境变量"""
        # 优先使用管理后台配置的 session_token
        session_token = self.flow_config.get("session_token", "").strip()
        if session_token:
            return session_token
        
        # 如果管理后台没有配置，则使用环境变量
        env_token = env.flow_session_token or ""
        return env_token.strip()
    
    def get_csrf_token(self) -> str:
        """获取 csrf_token，优先使用管理后台配置，如果没有则使用环境变量"""
        # 优先使用管理后台配置的 csrf_token
        csrf_token = self.flow_config.get("csrf_token", "").strip()
        if csrf_token:
            return csrf_token
        
        # 如果管理后台没有配置，则使用环境变量
        env_token = env.flow_csrf_token or ""
        return env_token.strip()


# 全局实例
setting = ConfigManager()
