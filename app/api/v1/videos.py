"""媒体生成接口 - Flow API 视频和图片生成"""

import time
import base64
import uuid
from io import BytesIO
from typing import Dict, Any, Optional, List, Literal, Tuple
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from PIL import Image

from app.core.config import setting
from app.core.logger import logger
from app.core.auth import auth_manager
from app.services.flow.client import FlowClient
from app.services.flow.image_cache import image_upload_cache
from app.core.exception import GrokApiException
from app.core.r2 import upload_fileobj, get_public_url


router = APIRouter(tags=["媒体生成"])


class VideoImageObject(BaseModel):
    """视频图片对象"""
    url: str = Field(..., description="图片URL")


class VideoImageContent(BaseModel):
    """视频图片内容"""
    type: str = Field(default="image_url", description="类型固定image")
    image_url: VideoImageObject = Field(..., description="图片对象")
    role: Literal["first_frame", "last_frame", "reference_image"] = Field(..., description="图片角色")


class VideoGenerateRequest(BaseModel):
    """视频生成请求"""
    prompt: str
    images: Optional[List[VideoImageContent]] = Field(default=None, description="图片列表")
    aspect_ratio: Optional[Literal["VIDEO_ASPECT_RATIO_LANDSCAPE", "VIDEO_ASPECT_RATIO_PORTRAIT"]] = "VIDEO_ASPECT_RATIO_LANDSCAPE"
    seed: Optional[int] = None
    model: Optional[Literal["veo-3_1_fast", "veo-3_1_relaxed", "veo-3_1_quality"]] = "veo-3_1_fast"


class VideoStatusRequest(BaseModel):
    """视频状态查询请求"""
    operation_name: str
    scene_id: str


class ImageGenerateRequest(BaseModel):
    """图片生成请求"""
    prompt: str
    image: Optional[str] = None  # 图片 URL，如果提供则为图生图
    aspect_ratio: Optional[Literal["IMAGE_ASPECT_RATIO_LANDSCAPE", "IMAGE_ASPECT_RATIO_PORTRAIT"]] = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    seed: Optional[int] = None
    model: Optional[str] = "GEM_PIX_2"


def _convert_video_aspect_ratio_to_image(video_aspect_ratio: str) -> str:
    """将视频宽高比转换为图片宽高比"""
    if video_aspect_ratio == "VIDEO_ASPECT_RATIO_LANDSCAPE":
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"
    elif video_aspect_ratio == "VIDEO_ASPECT_RATIO_PORTRAIT":
        return "IMAGE_ASPECT_RATIO_PORTRAIT"
    else:
        # 默认返回横向
        return "IMAGE_ASPECT_RATIO_LANDSCAPE"


async def _get_media_id_from_url(url: str, access_token: str, aspect_ratio: str) -> str:
    """从URL获取mediaId（使用缓存）"""
    # 检查缓存
    cached_id = await image_upload_cache.get(url)
    if cached_id:
        logger.debug(f"[Video] 使用缓存的图片: {url[:50]}...")
        return cached_id
    
    # 下载图片
    image_bytes, mime_type = await FlowClient.download_image(url)
    
    # 转换为 base64
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    # 将视频宽高比转换为图片宽高比
    image_aspect_ratio = _convert_video_aspect_ratio_to_image(aspect_ratio)
    
    # 上传图片
    media_id = await FlowClient.upload_image(
        access_token=access_token,
        image_base64=image_base64,
        mime_type=mime_type,
        aspect_ratio=image_aspect_ratio
    )
    
    # 保存到缓存
    await image_upload_cache.set(url, media_id)
    logger.debug(f"[Video] 图片上传成功: {media_id[:50]}...")
    
    return media_id


async def _get_image_dimensions(image_bytes: bytes) -> Tuple[int, int]:
    """从图片字节数据中读取宽高
    
    Args:
        image_bytes: 图片字节数据
        
    Returns:
        (width, height)
    """
    try:
        image = Image.open(BytesIO(image_bytes))
        return image.size  # (width, height)
    except Exception as e:
        logger.warning(f"[Image] 读取图片尺寸失败: {e}")
        return (0, 0)


async def _upload_to_r2(file_url: str, file_type: str = "image", file_bytes: Optional[bytes] = None, mime_type: Optional[str] = None) -> Optional[str]:
    """下载文件并上传到 R2
    
    Args:
        file_url: 文件 URL
        file_type: 文件类型 ("image" 或 "video")
        file_bytes: 可选的已下载文件字节数据，如果提供则跳过下载
        mime_type: 可选的 MIME 类型，如果提供 file_bytes 则必须提供
        
    Returns:
        R2 公开链接，如果上传失败或未配置则返回 None
    """
    try:
        from app.core.env import env
        
        # 检查 R2 配置
        if not all([env.r2_endpoint_url, env.r2_access_key_id, env.r2_secret_access_key, env.r2_public_url]):
            logger.debug("[R2] R2 未配置，跳过上传")
            return None
        
        # 下载文件（如果未提供）
        if file_bytes is None:
            if file_type == "image":
                file_bytes, mime_type = await FlowClient.download_image(file_url)
            else:
                # 下载视频
                file_bytes, mime_type = await FlowClient.download_video(file_url)
        
        # 生成 R2 对象键
        file_ext = ".jpg" if file_type == "image" else ".mp4"
        if "image/png" in mime_type:
            file_ext = ".png"
        elif "image/webp" in mime_type:
            file_ext = ".webp"
        
        object_key = f"{file_type}s/{uuid.uuid4()}{file_ext}"
        
        # 上传到 R2
        await upload_fileobj(file_bytes, object_key, content_type=mime_type)
        logger.debug(f"[R2] 文件上传成功: {object_key}")
        
        # 获取公开链接
        r2_url = get_public_url(object_key)
        logger.debug(f"[R2] 公开链接: {r2_url}")
        
        return r2_url
        
    except ValueError as e:
        # R2 未配置
        logger.debug(f"[R2] R2 未配置: {e}")
        return None
    except Exception as e:
        logger.error(f"[R2] 上传文件失败: {e}")
        return None


@router.post("/v1/video/generations")
async def generate_video(
    request: VideoGenerateRequest,
    _: Optional[str] = Depends(auth_manager.verify)
) -> Dict[str, Any]:
    """生成视频（统一接口，支持文生视频、参考图片、起始图片、起始结束图片）"""
    try:
        logger.debug(f"[Video] 生成视频请求: {request.prompt[:50]}...")
        
        # 获取 session_token
        session_token = setting.get_session_token()
        if not session_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": "Session token 未配置，请在管理后台配置",
                        "type": "configuration_error",
                        "code": "NO_SESSION_TOKEN"
                    }
                }
            )
        
        # 获取 csrf_token（可选）
        csrf_token = setting.get_csrf_token() or None
        
        # 获取 access_token
        access_token = await FlowClient.get_access_token(session_token, csrf_token)
        
        # 获取或创建项目
        project_id = await FlowClient.get_or_create_project(session_token, csrf_token)
        
        # 处理图片，获取mediaId
        first_frame_id = None
        last_frame_id = None
        reference_image_ids = []
        
        if request.images:
            for img_content in request.images:
                media_id = await _get_media_id_from_url(
                    img_content.image_url.url,
                    access_token,
                    request.aspect_ratio
                )
                
                if img_content.role == "first_frame":
                    first_frame_id = media_id
                elif img_content.role == "last_frame":
                    last_frame_id = media_id
                elif img_content.role == "reference_image":
                    reference_image_ids.append(media_id)
        
        # 根据图片类型选择生成方式
        if first_frame_id and last_frame_id:
            # 起始和结束图片
            result = await FlowClient.generate_video_start_end(
                access_token=access_token,
                project_id=project_id,
                prompt=request.prompt,
                start_image_id=first_frame_id,
                end_image_id=last_frame_id,
                aspect_ratio=request.aspect_ratio,
                seed=request.seed,
                model=request.model
            )
        elif first_frame_id:
            # 起始图片
            result = await FlowClient.generate_video_start(
                access_token=access_token,
                project_id=project_id,
                prompt=request.prompt,
                start_image_id=first_frame_id,
                aspect_ratio=request.aspect_ratio,
                seed=request.seed,
                model=request.model
            )
        elif reference_image_ids:
            # 参考图片
            result = await FlowClient.generate_video_reference(
                access_token=access_token,
                project_id=project_id,
                prompt=request.prompt,
                reference_image_ids=reference_image_ids,
                aspect_ratio=request.aspect_ratio,
                seed=request.seed,
                model=request.model
            )
        else:
            # 文生视频
            result = await FlowClient.generate_video(
                access_token=access_token,
                project_id=project_id,
                prompt=request.prompt,
                aspect_ratio=request.aspect_ratio,
                seed=request.seed,
                model=request.model
            )
        
        operations = result.get("operations", [])
        if not operations:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "message": "生成视频失败: 未返回操作信息",
                        "type": "internal_error",
                        "code": "GENERATION_ERROR"
                    }
                }
            )
        
        operation = operations[0]
        operation_name = operation.get("operation", {}).get("name")
        scene_id = operation.get("sceneId")
        status = operation.get("status")
        
        logger.debug(f"[Video] 视频生成请求已提交: {operation_name}")
        
        return {
            "id": operation_name,
            "object": "video.generation",
            "created": int(time.time()),
            "status": status.lower().replace("_", " ") if status else "pending",
            "prompt": request.prompt,
            "scene_id": scene_id,
            "project_id": project_id,
            "remaining_credits": result.get("remainingCredits", 0)
        }
        
    except GrokApiException as e:
        logger.error(f"[Video] 生成视频失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "api_error",
                    "code": e.error_code
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Video] 生成视频异常: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": f"生成视频失败: {e}",
                    "type": "internal_error",
                    "code": "GENERATION_ERROR"
                }
            }
        )


@router.get("/v1/video/generations/{generation_id}")
async def get_video_status(
    generation_id: str,
    scene_id: str,
    _: Optional[str] = Depends(auth_manager.verify)
) -> Dict[str, Any]:
    """查询视频生成状态"""
    try:
        logger.debug(f"[Video] 查询状态: {generation_id}")
        
        # 获取 session_token
        session_token = setting.get_session_token()
        if not session_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": "Session token 未配置",
                        "type": "configuration_error",
                        "code": "NO_SESSION_TOKEN"
                    }
                }
            )
        
        # 获取 access_token
        access_token = await FlowClient.get_access_token(session_token)
        
        # 构建操作列表
        operations = [{
            "operation": {
                "name": generation_id
            },
            "sceneId": scene_id,
            "status": "MEDIA_GENERATION_STATUS_PENDING"
        }]
        
        # 查询状态
        result = await FlowClient.check_video_status(access_token, operations)
        
        operations_result = result.get("operations", [])
        if not operations_result:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "message": "未找到生成任务",
                        "type": "not_found",
                        "code": "GENERATION_NOT_FOUND"
                    }
                }
            )
        
        operation_result = operations_result[0]
        status = operation_result.get("status", "")
        status_lower = status.lower().replace("_", " ")
        
        response = {
            "id": generation_id,
            "object": "video.generation",
            "status": status_lower,
            "scene_id": scene_id,
            "remaining_credits": result.get("remainingCredits", 0)
        }
        
        # 如果生成成功，返回视频信息
        if status == "MEDIA_GENERATION_STATUS_SUCCESSFUL":
            operation_data = operation_result.get("operation", {})
            metadata = operation_data.get("metadata", {})
            video_data = metadata.get("video", {})
            
            fife_url = video_data.get("fifeUrl")
            
            # 上传到 R2
            r2_url = None
            if fife_url:
                try:
                    r2_url = await _upload_to_r2(fife_url, "video")
                except Exception as e:
                    logger.warning(f"[Video] 上传到 R2 失败: {e}")
            
            response.update({
                "video": {
                    "media_generation_id": operation_result.get("mediaGenerationId"),
                    "fife_url": fife_url,
                    "url": r2_url or fife_url,  # 优先返回 R2 链接
                    "serving_base_uri": video_data.get("servingBaseUri"),
                    "seed": video_data.get("seed"),
                    "model": video_data.get("model"),
                    "aspect_ratio": video_data.get("aspectRatio"),
                    "prompt": video_data.get("prompt")
                }
            })
        
        logger.debug(f"[Video] 状态查询完成: {status_lower}")
        return response
        
    except GrokApiException as e:
        logger.error(f"[Video] 查询状态失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "api_error",
                    "code": e.error_code
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Video] 查询状态异常: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": f"查询状态失败: {e}",
                    "type": "internal_error",
                    "code": "STATUS_ERROR"
                }
            }
        )


@router.get("/v1/video/credits")
async def get_credits(
    _: Optional[str] = Depends(auth_manager.verify)
) -> Dict[str, Any]:
    """获取余额信息"""
    try:
        logger.debug("[Video] 查询余额")
        
        # 获取 session_token
        session_token = setting.get_session_token()
        if not session_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": "Session token 未配置",
                        "type": "configuration_error",
                        "code": "NO_SESSION_TOKEN"
                    }
                }
            )
        
        # 获取 access_token
        access_token = await FlowClient.get_access_token(session_token)
        
        # 获取余额
        credits_data = await FlowClient.get_credits(access_token)
        
        return {
            "credits": credits_data.get("credits", 0),
            "user_paygate_tier": credits_data.get("userPaygateTier", "")
        }
        
    except GrokApiException as e:
        logger.error(f"[Video] 查询余额失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "api_error",
                    "code": e.error_code
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Video] 查询余额异常: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": f"查询余额失败: {e}",
                    "type": "internal_error",
                    "code": "CREDITS_ERROR"
                }
            }
        )


@router.post("/v1/images/generations")
async def generate_image(
    request: ImageGenerateRequest,
    _: Optional[str] = Depends(auth_manager.verify)
) -> Dict[str, Any]:
    """生成图片（文生图或图生图）"""
    try:
        logger.debug(f"[Image] 生成图片请求: {request.prompt[:50]}...")
        
        # 获取 session_token
        session_token = setting.get_session_token()
        if not session_token:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": {
                        "message": "Session token 未配置，请在管理后台配置",
                        "type": "configuration_error",
                        "code": "NO_SESSION_TOKEN"
                    }
                }
            )
        
        # 获取 csrf_token（可选）
        csrf_token = setting.get_csrf_token() or None
        
        # 获取 access_token
        access_token = await FlowClient.get_access_token(session_token, csrf_token)
        
        # 获取或创建项目
        project_id = await FlowClient.get_or_create_project(session_token, csrf_token)
        
        # 如果是图生图，先检查缓存，然后下载并上传图片
        reference_image_id = None
        if request.image:
            image_url = request.image
            
            # 检查缓存
            cached_id = await image_upload_cache.get(image_url)
            if cached_id:
                reference_image_id = cached_id
                logger.debug(f"[Image] 使用缓存的参考图片: {reference_image_id[:50]}...")
            else:
                # 下载图片
                image_bytes, mime_type = await FlowClient.download_image(image_url)
                
                # 转换为 base64
                image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                
                # 上传图片
                reference_image_id = await FlowClient.upload_image(
                    access_token=access_token,
                    image_base64=image_base64,
                    mime_type=mime_type,
                    aspect_ratio=request.aspect_ratio
                )
                
                # 保存到缓存
                await image_upload_cache.set(image_url, reference_image_id)
                logger.debug(f"[Image] 参考图片上传成功: {reference_image_id[:50]}...")
        
        # 生成图片
        result = await FlowClient.generate_image(
            access_token=access_token,
            project_id=project_id,
            prompt=request.prompt,
            reference_image_id=reference_image_id,
            aspect_ratio=request.aspect_ratio,
            seed=request.seed
        )
        
        media_list = result.get("media", [])
        if not media_list:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": {
                        "message": "生成图片失败: 未返回图片信息",
                        "type": "internal_error",
                        "code": "GENERATION_ERROR"
                    }
                }
            )
        
        media = media_list[0]
        image_data_obj = media.get("image", {}).get("generatedImage", {})
        
        media_generation_id = image_data_obj.get("mediaGenerationId")
        fife_url = image_data_obj.get("fifeUrl")
        encoded_image = image_data_obj.get("encodedImage")
        
        logger.debug(f"[Image] 图片生成成功: {media_generation_id[:50] if media_generation_id else 'unknown'}...")
        
        # 上传到 R2 并读取图片尺寸
        r2_url = None
        width = 0
        height = 0
        if fife_url:
            try:
                # 下载图片以获取尺寸
                image_bytes, mime_type = await FlowClient.download_image(fife_url)
                width, height = await _get_image_dimensions(image_bytes)
                
                # 上传到 R2（复用已下载的图片数据）
                r2_url = await _upload_to_r2(fife_url, "image", file_bytes=image_bytes, mime_type=mime_type)
            except Exception as e:
                logger.warning(f"[Image] 上传到 R2 或读取尺寸失败: {e}")
        
        response = {
            "id": media_generation_id,
            "object": "image.generation",
            "created": int(time.time()),
            "prompt": request.prompt,
            "project_id": project_id,
            "media_generation_id": media_generation_id,
            "fife_url": fife_url,
            "url": r2_url or fife_url,  # 优先返回 R2 链接
            "aspect_ratio": image_data_obj.get("aspectRatio"),
            "seed": image_data_obj.get("seed"),
            "model": image_data_obj.get("modelNameType"),
            "width": width,
            "height": height
        }
        
        # 如果返回了 base64 编码的图片，也包含在响应中
        # if encoded_image:
        #     response["b64_json"] = encoded_image
        
        return response
        
    except GrokApiException as e:
        logger.error(f"[Image] 生成图片失败: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": str(e),
                    "type": "api_error",
                    "code": e.error_code
                }
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Image] 生成图片异常: {e}")
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "message": f"生成图片失败: {e}",
                    "type": "internal_error",
                    "code": "GENERATION_ERROR"
                }
            }
        )

