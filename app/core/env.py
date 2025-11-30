"""环境变量读取模块"""

import os
from typing import Optional
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()


class Env:
    """环境变量读取类"""

    @property
    def r2_endpoint_url(self) -> Optional[str]:
        """R2 端点 URL"""
        return os.getenv("R2_ENDPOINT_URL")

    @property
    def r2_access_key_id(self) -> Optional[str]:
        """R2 访问密钥 ID"""
        return os.getenv("R2_ACCESS_KEY_ID")

    @property
    def r2_secret_access_key(self) -> Optional[str]:
        """R2 机密访问密钥"""
        return os.getenv("R2_SECRET_ACCESS_KEY")

    @property
    def r2_bucket_name(self) -> Optional[str]:
        """R2 存储桶名称"""
        return os.getenv("R2_BUCKET_NAME")

    @property
    def r2_public_url(self) -> Optional[str]:
        """R2 公开访问 URL"""
        return os.getenv("R2_PUBLIC_URL")


# 全局实例
env = Env()

