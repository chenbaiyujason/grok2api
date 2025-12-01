"""FastAPI应用主入口"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.logger import logger
from app.core.exception import register_exception_handlers
from app.core.storage import storage_manager
from app.core.config import setting
from app.api.v1.videos import router as videos_router
from app.api.admin.manage import router as admin_router
from app.services.flow.image_cache import image_upload_cache

# 2. 定义应用生命周期
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    启动顺序:
    1. 初始化核心服务 (storage, settings)
    
    关闭顺序:
    1. 关闭核心服务
    """
    # --- 启动过程 ---
    # 1. 初始化核心服务
    await storage_manager.init()

    # 设置存储到配置
    storage = storage_manager.get_storage()
    setting.set_storage(storage)
    
    # 重新加载配置
    await setting.reload()
    
    # 初始化图片上传缓存
    await image_upload_cache.init()
    
    logger.info("[Flow2API] 核心服务初始化完成")

    logger.info("[Flow2API] 应用启动成功")
    
    try:
        yield
    finally:
        # --- 关闭过程 ---
        # 关闭核心服务
        await storage_manager.close()
        logger.info("[Flow2API] 应用关闭成功")


# 初始化日志
logger.info("[Flow2API] 应用正在启动...")

# 创建FastAPI应用
app = FastAPI(
    title="Flow2API",
    description="Flow API 视频生成服务",
    version="1.0.0",
    lifespan=lifespan
)

# 注册全局异常处理器
register_exception_handlers(app)

# 注册路由
app.include_router(videos_router)
app.include_router(admin_router)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="app/template"), name="template")

@app.get("/")
async def root():
    """根路径"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login")


@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "Flow2API",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)