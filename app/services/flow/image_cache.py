"""图片上传缓存服务 - 缓存 URL 到 mediaGenerationId 的映射"""

import asyncio
import hashlib
import orjson
import aiofiles
from pathlib import Path
from typing import Optional, Dict, Any

from app.core.logger import logger
from app.core.storage import storage_manager


class ImageUploadCache:
    """图片上传缓存"""
    
    def __init__(self):
        self._cache_file: Optional[Path] = None
        self._cache: Dict[str, str] = {}  # url_hash -> mediaGenerationId
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def init(self) -> None:
        """初始化缓存"""
        if self._initialized:
            return
        
        try:
            storage = storage_manager.get_storage()
            data_dir = storage.data_dir if hasattr(storage, 'data_dir') else Path(__file__).parents[3] / "data"
            self._cache_file = data_dir / "image_upload_cache.json"
            
            # 加载缓存
            await self._load_cache()
            self._initialized = True
            logger.debug("[ImageUploadCache] 缓存初始化完成")
        except Exception as e:
            logger.warning(f"[ImageUploadCache] 初始化失败: {e}, 使用内存缓存")
            self._initialized = True
    
    def _hash_url(self, url: str) -> str:
        """对 URL 进行哈希"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()
    
    async def _load_cache(self) -> None:
        """加载缓存"""
        if not self._cache_file or not self._cache_file.exists():
            self._cache = {}
            return
        
        try:
            async with self._lock:
                async with aiofiles.open(self._cache_file, "r", encoding="utf-8") as f:
                    content = await f.read()
                    self._cache = orjson.loads(content)
            logger.debug(f"[ImageUploadCache] 加载缓存: {len(self._cache)} 条记录")
        except Exception as e:
            logger.warning(f"[ImageUploadCache] 加载缓存失败: {e}")
            self._cache = {}
    
    async def _save_cache(self) -> None:
        """保存缓存"""
        if not self._cache_file:
            return
        
        try:
            async with self._lock:
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                async with aiofiles.open(self._cache_file, "w", encoding="utf-8") as f:
                    await f.write(orjson.dumps(self._cache, option=orjson.OPT_INDENT_2).decode())
            logger.debug(f"[ImageUploadCache] 保存缓存: {len(self._cache)} 条记录")
        except Exception as e:
            logger.warning(f"[ImageUploadCache] 保存缓存失败: {e}")
    
    async def get(self, url: str) -> Optional[str]:
        """获取缓存的 mediaGenerationId"""
        if not self._initialized:
            await self.init()
        
        url_hash = self._hash_url(url)
        media_id = self._cache.get(url_hash)
        
        if media_id:
            logger.debug(f"[ImageUploadCache] 缓存命中: {url[:50]}...")
        
        return media_id
    
    async def set(self, url: str, media_generation_id: str) -> None:
        """设置缓存"""
        if not self._initialized:
            await self.init()
        
        url_hash = self._hash_url(url)
        self._cache[url_hash] = media_generation_id
        await self._save_cache()
        logger.debug(f"[ImageUploadCache] 缓存已保存: {url[:50]}... -> {media_generation_id[:50]}...")


# 全局实例
image_upload_cache = ImageUploadCache()

