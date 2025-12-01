"""Flow API 客户端 - 处理视频生成请求"""

import asyncio
import orjson
from typing import Dict, Any, Optional, Tuple, List
from curl_cffi import requests as curl_requests
from datetime import datetime

from app.core.logger import logger
from app.core.exception import GrokApiException


# 常量
SESSION_URL = "https://labs.google/fx/api/auth/session"
CREDITS_URL = "https://aisandbox-pa.googleapis.com/v1/credits"
USER_PROJECTS_URL = "https://labs.google/fx/api/trpc/project.searchUserProjects"
CREATE_PROJECT_URL = "https://labs.google/fx/api/trpc/project.createProject"
GENERATE_VIDEO_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoText"
GENERATE_VIDEO_REFERENCE_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoReferenceImages"
GENERATE_VIDEO_START_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartImage"
GENERATE_VIDEO_START_END_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchAsyncGenerateVideoStartAndEndImage"
CHECK_STATUS_URL = "https://aisandbox-pa.googleapis.com/v1/video:batchCheckAsyncVideoGenerationStatus"
UPLOAD_IMAGE_URL = "https://aisandbox-pa.googleapis.com/v1:uploadUserImage"
GENERATE_IMAGE_URL_TEMPLATE = "https://aisandbox-pa.googleapis.com/v1/projects/{project_id}/flowMedia:batchGenerateImages"
TIMEOUT = 120
BROWSER = "chrome133a"
MAX_RETRY = 3
RETRY_DELAY = 5  # 429错误重试延迟（秒）


class FlowClient:
    """Flow API 客户端"""
    
    @staticmethod
    def _get_video_model_key(
        model: str,
        aspect_ratio: str,
        has_start_image: bool = False,
        has_end_image: bool = False,
        has_reference_images: bool = False
    ) -> str:
        """根据模型、宽高比和图片类型生成 videoModelKey
        
        Args:
            model: 模型名称 (veo-3_1_fast, veo-3_1_relaxed, veo-3_1_quality)
            aspect_ratio: 宽高比 (VIDEO_ASPECT_RATIO_LANDSCAPE, VIDEO_ASPECT_RATIO_PORTRAIT)
            has_start_image: 是否有起始图片
            has_end_image: 是否有结束图片
            has_reference_images: 是否有参考图片
            
        Returns:
            videoModelKey
        """
        is_landscape = aspect_ratio == "VIDEO_ASPECT_RATIO_LANDSCAPE"
        
        # 参考图片生成（只支持横屏）
        if has_reference_images:
            if model == "veo-3_1_quality":
                raise GrokApiException("quality 模型不支持参考图片生成", "UNSUPPORTED_MODEL")
            base_key = "veo_3_0_r2v_fast_ultra"
            if model == "veo-3_1_relaxed":
                base_key += "_relaxed"
            return base_key
        
        # 首尾帧生成
        if has_start_image and has_end_image:
            if model == "veo-3_1_fast":
                if is_landscape:
                    base_key = "veo_3_1_i2v_s_fast_ultra_fl"
                else:
                    base_key = "veo_3_1_i2v_s_fast_portrait_ultra_fl"
            elif model == "veo-3_1_relaxed":
                if is_landscape:
                    base_key = "veo_3_1_i2v_s_fast_ultra_fl_relaxed"
                else:
                    base_key = "veo_3_1_i2v_s_fast_portrait_ultra_fl_relaxed"
            else:  # quality
                if is_landscape:
                    base_key = "veo_3_1_i2v_s_fl"
                else:
                    base_key = "veo_3_1_i2v_s_portrait_fl"
            return base_key
        
        # 首帧生成
        if has_start_image:
            if model == "veo-3_1_fast":
                if is_landscape:
                    base_key = "veo_3_1_i2v_s_fast_ultra"
                else:
                    base_key = "veo_3_1_i2v_s_fast_portrait"
            elif model == "veo-3_1_relaxed":
                if is_landscape:
                    base_key = "veo_3_1_i2v_s_fast_ultra_relaxed"
                else:
                    base_key = "veo_3_1_i2v_s_fast_portrait_relaxed"
            else:  # quality
                if is_landscape:
                    base_key = "veo_3_1_i2v_s"
                else:
                    base_key = "veo_3_1_i2v_s_portrait"
            return base_key
        
        # 文生视频
        if model == "veo-3_1_fast":
            if is_landscape:
                base_key = "veo_3_1_t2v_fast_ultra"
            else:
                base_key = "veo_3_1_t2v_fast_portrait_ultra"
        elif model == "veo-3_1_relaxed":
            if is_landscape:
                base_key = "veo_3_1_t2v_fast_ultra_relaxed"
            else:
                base_key = "veo_3_1_t2v_fast_portrait_ultra_relaxed"
        else:  # quality
            base_key = "veo_3_1_t2v"
        
        return base_key
    """Flow API 客户端"""

    @staticmethod
    async def get_access_token(session_token: str) -> str:
        """获取 access_token
        
        Args:
            session_token: __Secure-next-auth.session-token
            
        Returns:
            access_token
        """
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "content-type": "application/json",
                "pragma": "no-cache",
                "cookie": f"__Secure-next-auth.session-token={session_token}",
                "Referer": "https://labs.google/fx/tools/flow"
            }
            
            response = await asyncio.to_thread(
                curl_requests.get,
                SESSION_URL,
                headers=headers,
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"获取 access_token 失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            access_token = data.get("access_token")
            
            if not access_token:
                raise GrokApiException("access_token 不存在", "NO_ACCESS_TOKEN")
            
            logger.debug("[Flow] 成功获取 access_token")
            return access_token
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 获取 access_token 失败: {e}")
            raise GrokApiException(f"获取 access_token 失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def get_credits(access_token: str) -> Dict[str, Any]:
        """获取余额信息
        
        Args:
            access_token: 访问令牌
            
        Returns:
            余额信息
        """
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "authorization": f"Bearer {access_token}",
                "cache-control": "no-cache",
                "pragma": "no-cache",
                "Referer": "https://labs.google/"
            }
            
            response = await asyncio.to_thread(
                curl_requests.get,
                CREDITS_URL,
                headers=headers,
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"获取余额失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            logger.debug(f"[Flow] 余额: {data.get('credits', 0)}")
            return data
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 获取余额失败: {e}")
            raise GrokApiException(f"获取余额失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def get_user_projects(session_token: str) -> Dict[str, Any]:
        """获取用户项目列表
        
        Args:
            session_token: __Secure-next-auth.session-token
            
        Returns:
            项目列表
        """
        try:
            # URL 编码的输入参数
            input_param = orjson.dumps({
                "json": {
                    "pageSize": 20,
                    "toolName": "PINHOLE",
                    "cursor": None
                },
                "meta": {
                    "values": {
                        "cursor": ["undefined"]
                    }
                }
            }).decode('utf-8')
            
            import urllib.parse
            encoded_input = urllib.parse.quote(input_param)
            url = f"{USER_PROJECTS_URL}?input={encoded_input}"
            
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "content-type": "application/json",
                "pragma": "no-cache",
                "cookie": f"__Secure-next-auth.session-token={session_token}",
                "Referer": "https://labs.google/fx/tools/flow"
            }
            
            response = await asyncio.to_thread(
                curl_requests.get,
                url,
                headers=headers,
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"获取项目列表失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            logger.debug("[Flow] 成功获取项目列表")
            return data
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 获取项目列表失败: {e}")
            raise GrokApiException(f"获取项目列表失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def get_latest_project(session_token: str) -> Optional[str]:
        """获取最新的项目 ID
        
        Args:
            session_token: __Secure-next-auth.session-token
            
        Returns:
            项目 ID，如果没有则返回 None
        """
        try:
            data = await FlowClient.get_user_projects(session_token)
            
            projects = data.get("result", {}).get("data", {}).get("json", {}).get("result", {}).get("projects", [])
            
            if not projects:
                logger.debug("[Flow] 没有找到项目")
                return None
            
            # 按创建时间排序，获取最新的
            sorted_projects = sorted(
                projects,
                key=lambda x: x.get("creationTime", ""),
                reverse=True
            )
            
            latest_project_id = sorted_projects[0].get("projectId")
            logger.debug(f"[Flow] 最新项目 ID: {latest_project_id}")
            return latest_project_id
            
        except Exception as e:
            logger.error(f"[Flow] 获取最新项目失败: {e}")
            return None

    @staticmethod
    async def create_project(session_token: str, project_title: Optional[str] = None) -> str:
        """创建新项目
        
        Args:
            session_token: __Secure-next-auth.session-token
            project_title: 项目标题，如果不提供则使用时间戳
            
        Returns:
            项目 ID
        """
        try:
            if not project_title:
                # 生成默认标题，格式：Dec 01 - 17:12
                now = datetime.now()
                project_title = now.strftime("%b %d - %H:%M")
            
            body = {
                "json": {
                    "projectTitle": project_title,
                    "toolName": "PINHOLE"
                }
            }
            
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "cache-control": "no-cache",
                "content-type": "application/json",
                "pragma": "no-cache",
                "cookie": f"__Secure-next-auth.session-token={session_token}",
                "Referer": "https://labs.google/fx/tools/flow"
            }
            
            response = await asyncio.to_thread(
                curl_requests.post,
                CREATE_PROJECT_URL,
                headers=headers,
                json=body,
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"创建项目失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            project_id = data.get("result", {}).get("data", {}).get("json", {}).get("result", {}).get("projectId")
            
            if not project_id:
                raise GrokApiException("创建项目失败: 未返回项目 ID", "CREATE_PROJECT_ERROR")
            
            logger.debug(f"[Flow] 成功创建项目: {project_id}")
            return project_id
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 创建项目失败: {e}")
            raise GrokApiException(f"创建项目失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def get_or_create_project(session_token: str) -> str:
        """获取或创建项目
        
        Args:
            session_token: __Secure-next-auth.session-token
            
        Returns:
            项目 ID
        """
        project_id = await FlowClient.get_latest_project(session_token)
        
        if not project_id:
            project_id = await FlowClient.create_project(session_token)
        
        return project_id

    @staticmethod
    async def generate_video(
        access_token: str,
        project_id: str,
        prompt: str,
        scene_id: Optional[str] = None,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        user_paygate_tier: str = "PAYGATE_TIER_ONE",
        model: str = "veo-3_1_fast"
    ) -> Dict[str, Any]:
        """生成视频
        
        Args:
            access_token: 访问令牌
            project_id: 项目 ID
            prompt: 提示词
            scene_id: 场景 ID，如果不提供则自动生成
            aspect_ratio: 宽高比
            seed: 随机种子
            user_paygate_tier: 用户付费等级
            model: 模型名称 (veo-3_1_fast, veo-3_1_relaxed, veo-3_1_quality)
            
        Returns:
            生成结果
        """
        import uuid
        import random
        
        if not scene_id:
            scene_id = str(uuid.uuid4())
        
        if seed is None:
            seed = random.randint(1, 99999)
        
        video_model_key = FlowClient._get_video_model_key(
            model=model,
            aspect_ratio=aspect_ratio,
            has_start_image=False,
            has_end_image=False,
            has_reference_images=False
        )
        
        body = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE",
                "userPaygateTier": user_paygate_tier
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "seed": seed,
                "textInput": {
                    "prompt": prompt
                },
                "videoModelKey": video_model_key,
                "metadata": {
                    "sceneId": scene_id
                }
            }]
        }
        
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {access_token}",
            "cache-control": "no-cache",
            "content-type": "text/plain;charset=UTF-8",
            "pragma": "no-cache",
            "Referer": "https://labs.google/"
        }
        
        # 重试逻辑处理 429 错误
        for attempt in range(MAX_RETRY):
            try:
                response = await asyncio.to_thread(
                    curl_requests.post,
                    GENERATE_VIDEO_URL,
                    headers=headers,
                    data=orjson.dumps(body),
                    impersonate=BROWSER,
                    timeout=TIMEOUT
                )
                
                # 检查 429 错误
                if response.status_code == 429:
                    error_data = response.json() if response.content else {}
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == 429 or error_info.get("status") == "RESOURCE_EXHAUSTED":
                        if attempt < MAX_RETRY - 1:
                            wait_time = RETRY_DELAY * (attempt + 1)
                            logger.warning(f"[Flow] 遇到并发限制，等待 {wait_time} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRY})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise GrokApiException(
                                "生成视频失败: 达到并发限制，请稍后重试",
                                "RATE_LIMIT_ERROR",
                                {"status": 429, "error": error_data}
                            )
                
                if response.status_code != 200:
                    raise GrokApiException(
                        f"生成视频失败: {response.status_code}",
                        "HTTP_ERROR",
                        {"status": response.status_code}
                    )
                
                data = response.json()
                logger.debug(f"[Flow] 视频生成请求已提交: {data.get('operations', [{}])[0].get('operation', {}).get('name', 'unknown')}")
                return data
                
            except curl_requests.RequestsError as e:
                if attempt < MAX_RETRY - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"[Flow] 网络错误，等待 {wait_time} 秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"[Flow] 网络错误: {e}")
                raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
            except GrokApiException:
                raise
            except Exception as e:
                logger.error(f"[Flow] 生成视频失败: {e}")
                raise GrokApiException(f"生成视频失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def generate_video_reference(
        access_token: str,
        project_id: str,
        prompt: str,
        reference_image_ids: List[str],
        scene_id: Optional[str] = None,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        user_paygate_tier: str = "PAYGATE_TIER_ONE",
        model: str = "veo-3_1_fast"
    ) -> Dict[str, Any]:
        """生成视频（参考图片）"""
        import uuid
        import random
        
        if not scene_id:
            scene_id = str(uuid.uuid4())
        
        if seed is None:
            seed = random.randint(1, 99999)
        
        video_model_key = FlowClient._get_video_model_key(
            model=model,
            aspect_ratio=aspect_ratio,
            has_start_image=False,
            has_end_image=False,
            has_reference_images=True
        )
        
        body = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE",
                "userPaygateTier": user_paygate_tier
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "seed": seed,
                "textInput": {
                    "prompt": prompt
                },
                "videoModelKey": video_model_key,
                "referenceImages": [
                    {
                        "imageUsageType": "IMAGE_USAGE_TYPE_ASSET",
                        "mediaId": media_id
                    }
                    for media_id in reference_image_ids
                ],
                "metadata": {
                    "sceneId": scene_id
                }
            }]
        }
        
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {access_token}",
            "cache-control": "no-cache",
            "content-type": "text/plain;charset=UTF-8",
            "pragma": "no-cache",
            "Referer": "https://labs.google/"
        }
        
        # 重试逻辑处理 429 错误
        for attempt in range(MAX_RETRY):
            try:
                response = await asyncio.to_thread(
                    curl_requests.post,
                    GENERATE_VIDEO_REFERENCE_URL,
                    headers=headers,
                    data=orjson.dumps(body),
                    impersonate=BROWSER,
                    timeout=TIMEOUT
                )
                
                # 检查 429 错误
                if response.status_code == 429:
                    error_data = response.json() if response.content else {}
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == 429 or error_info.get("status") == "RESOURCE_EXHAUSTED":
                        if attempt < MAX_RETRY - 1:
                            wait_time = RETRY_DELAY * (attempt + 1)
                            logger.warning(f"[Flow] 遇到并发限制，等待 {wait_time} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRY})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise GrokApiException(
                                "生成视频失败: 达到并发限制，请稍后重试",
                                "RATE_LIMIT_ERROR",
                                {"status": 429, "error": error_data}
                            )
                
                if response.status_code != 200:
                    raise GrokApiException(
                        f"生成视频失败: {response.status_code}",
                        "HTTP_ERROR",
                        {"status": response.status_code}
                    )
                
                data = response.json()
                logger.debug("[Flow] 参考图片视频生成请求已提交")
                return data
                
            except curl_requests.RequestsError as e:
                if attempt < MAX_RETRY - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"[Flow] 网络错误，等待 {wait_time} 秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"[Flow] 网络错误: {e}")
                raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
            except GrokApiException:
                raise
            except Exception as e:
                logger.error(f"[Flow] 生成视频失败: {e}")
                raise GrokApiException(f"生成视频失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def generate_video_start(
        access_token: str,
        project_id: str,
        prompt: str,
        start_image_id: str,
        scene_id: Optional[str] = None,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        user_paygate_tier: str = "PAYGATE_TIER_ONE",
        model: str = "veo-3_1_fast"
    ) -> Dict[str, Any]:
        """生成视频（起始图片）"""
        import uuid
        import random
        
        if not scene_id:
            scene_id = str(uuid.uuid4())
        
        if seed is None:
            seed = random.randint(1, 99999)
        
        video_model_key = FlowClient._get_video_model_key(
            model=model,
            aspect_ratio=aspect_ratio,
            has_start_image=True,
            has_end_image=False,
            has_reference_images=False
        )
        
        body = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE",
                "userPaygateTier": user_paygate_tier
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "seed": seed,
                "textInput": {
                    "prompt": prompt
                },
                "videoModelKey": video_model_key,
                "startImage": {
                    "mediaId": start_image_id
                },
                "metadata": {
                    "sceneId": scene_id
                }
            }]
        }
        
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {access_token}",
            "cache-control": "no-cache",
            "content-type": "text/plain;charset=UTF-8",
            "pragma": "no-cache",
            "Referer": "https://labs.google/"
        }
        
        # 重试逻辑处理 429 错误
        for attempt in range(MAX_RETRY):
            try:
                response = await asyncio.to_thread(
                    curl_requests.post,
                    GENERATE_VIDEO_START_URL,
                    headers=headers,
                    data=orjson.dumps(body),
                    impersonate=BROWSER,
                    timeout=TIMEOUT
                )
                
                # 检查 429 错误
                if response.status_code == 429:
                    error_data = response.json() if response.content else {}
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == 429 or error_info.get("status") == "RESOURCE_EXHAUSTED":
                        if attempt < MAX_RETRY - 1:
                            wait_time = RETRY_DELAY * (attempt + 1)
                            logger.warning(f"[Flow] 遇到并发限制，等待 {wait_time} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRY})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise GrokApiException(
                                "生成视频失败: 达到并发限制，请稍后重试",
                                "RATE_LIMIT_ERROR",
                                {"status": 429, "error": error_data}
                            )
                
                if response.status_code != 200:
                    raise GrokApiException(
                        f"生成视频失败: {response.status_code}",
                        "HTTP_ERROR",
                        {"status": response.status_code}
                    )
                
                data = response.json()
                logger.debug("[Flow] 起始图片视频生成请求已提交")
                return data
                
            except curl_requests.RequestsError as e:
                if attempt < MAX_RETRY - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"[Flow] 网络错误，等待 {wait_time} 秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"[Flow] 网络错误: {e}")
                raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
            except GrokApiException:
                raise
            except Exception as e:
                logger.error(f"[Flow] 生成视频失败: {e}")
                raise GrokApiException(f"生成视频失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def generate_video_start_end(
        access_token: str,
        project_id: str,
        prompt: str,
        start_image_id: str,
        end_image_id: str,
        scene_id: Optional[str] = None,
        aspect_ratio: str = "VIDEO_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        user_paygate_tier: str = "PAYGATE_TIER_ONE",
        model: str = "veo-3_1_fast"
    ) -> Dict[str, Any]:
        """生成视频（起始和结束图片）"""
        import uuid
        import random
        
        if not scene_id:
            scene_id = str(uuid.uuid4())
        
        if seed is None:
            seed = random.randint(1, 99999)
        
        video_model_key = FlowClient._get_video_model_key(
            model=model,
            aspect_ratio=aspect_ratio,
            has_start_image=True,
            has_end_image=True,
            has_reference_images=False
        )
        
        body = {
            "clientContext": {
                "projectId": project_id,
                "tool": "PINHOLE",
                "userPaygateTier": user_paygate_tier
            },
            "requests": [{
                "aspectRatio": aspect_ratio,
                "seed": seed,
                "textInput": {
                    "prompt": prompt
                },
                "videoModelKey": video_model_key,
                "startImage": {
                    "mediaId": start_image_id
                },
                "endImage": {
                    "mediaId": end_image_id
                },
                "metadata": {
                    "sceneId": scene_id
                }
            }]
        }
        
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
            "authorization": f"Bearer {access_token}",
            "cache-control": "no-cache",
            "content-type": "text/plain;charset=UTF-8",
            "pragma": "no-cache",
            "Referer": "https://labs.google/"
        }
        
        # 重试逻辑处理 429 错误
        for attempt in range(MAX_RETRY):
            try:
                response = await asyncio.to_thread(
                    curl_requests.post,
                    GENERATE_VIDEO_START_END_URL,
                    headers=headers,
                    data=orjson.dumps(body),
                    impersonate=BROWSER,
                    timeout=TIMEOUT
                )
                
                # 检查 429 错误
                if response.status_code == 429:
                    error_data = response.json() if response.content else {}
                    error_info = error_data.get("error", {})
                    if error_info.get("code") == 429 or error_info.get("status") == "RESOURCE_EXHAUSTED":
                        if attempt < MAX_RETRY - 1:
                            wait_time = RETRY_DELAY * (attempt + 1)
                            logger.warning(f"[Flow] 遇到并发限制，等待 {wait_time} 秒后重试 (尝试 {attempt + 1}/{MAX_RETRY})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise GrokApiException(
                                "生成视频失败: 达到并发限制，请稍后重试",
                                "RATE_LIMIT_ERROR",
                                {"status": 429, "error": error_data}
                            )
                
                if response.status_code != 200:
                    raise GrokApiException(
                        f"生成视频失败: {response.status_code}",
                        "HTTP_ERROR",
                        {"status": response.status_code}
                    )
                
                data = response.json()
                logger.debug("[Flow] 起始结束图片视频生成请求已提交")
                return data
                
            except curl_requests.RequestsError as e:
                if attempt < MAX_RETRY - 1:
                    wait_time = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"[Flow] 网络错误，等待 {wait_time} 秒后重试: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                logger.error(f"[Flow] 网络错误: {e}")
                raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
            except GrokApiException:
                raise
            except Exception as e:
                logger.error(f"[Flow] 生成视频失败: {e}")
                raise GrokApiException(f"生成视频失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def check_video_status(
        access_token: str,
        operations: list
    ) -> Dict[str, Any]:
        """检查视频生成状态
        
        Args:
            access_token: 访问令牌
            operations: 操作列表，格式: [{"operation": {"name": "xxx"}, "sceneId": "xxx", "status": "xxx"}]
            
        Returns:
            状态信息
        """
        try:
            body = {
                "operations": operations
            }
            
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "authorization": f"Bearer {access_token}",
                "cache-control": "no-cache",
                "content-type": "text/plain;charset=UTF-8",
                "pragma": "no-cache",
                "Referer": "https://labs.google/"
            }
            
            response = await asyncio.to_thread(
                curl_requests.post,
                CHECK_STATUS_URL,
                headers=headers,
                data=orjson.dumps(body),
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"检查状态失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            return data
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 检查状态失败: {e}")
            raise GrokApiException(f"检查状态失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def download_image(url: str) -> Tuple[bytes, str]:
        """下载图片
        
        Args:
            url: 图片 URL
            
        Returns:
            (图片字节数据, MIME 类型)
        """
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = await asyncio.to_thread(
                curl_requests.get,
                url,
                headers=headers,
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"下载图片失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            # 检测 MIME 类型
            content_type = response.headers.get("content-type", "image/jpeg")
            if "image/" in content_type:
                mime_type = content_type
            else:
                # 根据内容判断
                content = response.content[:10]
                if content.startswith(b'\xff\xd8\xff'):
                    mime_type = "image/jpeg"
                elif content.startswith(b'\x89PNG'):
                    mime_type = "image/png"
                elif content.startswith(b'RIFF') and b'WEBP' in content:
                    mime_type = "image/webp"
                else:
                    mime_type = "image/jpeg"
            
            logger.debug(f"[Flow] 图片下载成功: {len(response.content)} bytes, {mime_type}")
            return response.content, mime_type
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 下载图片失败: {e}")
            raise GrokApiException(f"下载图片失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def download_video(url: str) -> Tuple[bytes, str]:
        """下载视频
        
        Args:
            url: 视频 URL
            
        Returns:
            (视频字节数据, MIME 类型)
        """
        try:
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = await asyncio.to_thread(
                curl_requests.get,
                url,
                headers=headers,
                impersonate=BROWSER,
                timeout=TIMEOUT * 3  # 视频下载可能需要更长时间
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"下载视频失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            # 检测 MIME 类型
            content_type = response.headers.get("content-type", "video/mp4")
            if "video/" in content_type:
                mime_type = content_type
            else:
                # 根据内容判断
                content = response.content[:12]
                if content.startswith(b'\x00\x00\x00\x20ftyp'):
                    mime_type = "video/mp4"
                elif content.startswith(b'RIFF') and b'WEBM' in content:
                    mime_type = "video/webm"
                else:
                    mime_type = "video/mp4"
            
            logger.debug(f"[Flow] 视频下载成功: {len(response.content)} bytes, {mime_type}")
            return response.content, mime_type
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 下载视频失败: {e}")
            raise GrokApiException(f"下载视频失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def upload_image(
        access_token: str,
        image_base64: str,
        mime_type: str = "image/jpeg",
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE"
    ) -> str:
        """上传图片
        
        Args:
            access_token: 访问令牌
            image_base64: base64 编码的图片数据（不包含 data:image/...;base64, 前缀）
            mime_type: 图片 MIME 类型
            aspect_ratio: 图片宽高比
            
        Returns:
            mediaGenerationId
        """
        try:
            body = {
                "imageInput": {
                    "rawImageBytes": image_base64,
                    "mimeType": mime_type,
                    "isUserUploaded": True,
                    "aspectRatio": aspect_ratio
                },
                "clientContext": {
                    "tool": "ASSET_MANAGER"
                }
            }
            
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "authorization": f"Bearer {access_token}",
                "cache-control": "no-cache",
                "content-type": "text/plain;charset=UTF-8",
                "pragma": "no-cache",
                "Referer": "https://labs.google/"
            }
            
            response = await asyncio.to_thread(
                curl_requests.post,
                UPLOAD_IMAGE_URL,
                headers=headers,
                data=orjson.dumps(body),
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"上传图片失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            media_generation_id = data.get("mediaGenerationId", {}).get("mediaGenerationId")
            
            if not media_generation_id:
                raise GrokApiException("上传图片失败: 未返回 mediaGenerationId", "UPLOAD_ERROR")
            
            logger.debug(f"[Flow] 图片上传成功: {media_generation_id[:50]}...")
            return media_generation_id
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 上传图片失败: {e}")
            raise GrokApiException(f"上传图片失败: {e}", "REQUEST_ERROR") from e

    @staticmethod
    async def generate_image(
        access_token: str,
        project_id: str,
        prompt: str,
        reference_image_id: Optional[str] = None,
        aspect_ratio: str = "IMAGE_ASPECT_RATIO_LANDSCAPE",
        seed: Optional[int] = None,
        image_model_name: str = "GEM_PIX_2"
    ) -> Dict[str, Any]:
        """生成图片（文生图或图生图）
        
        Args:
            access_token: 访问令牌
            project_id: 项目 ID
            prompt: 提示词
            reference_image_id: 参考图片的 mediaGenerationId，如果提供则为图生图，否则为文生图
            aspect_ratio: 图片宽高比
            seed: 随机种子
            image_model_name: 图片模型名称
            
        Returns:
            生成结果
        """
        try:
            if seed is None:
                import random
                seed = random.randint(1, 999999)
            
            request_data = {
                "seed": seed,
                "imageModelName": image_model_name,
                "imageAspectRatio": aspect_ratio,
                "prompt": prompt,
                "imageInputs": []
            }
            
            # 如果是图生图，添加参考图片
            if reference_image_id:
                request_data["imageInputs"] = [{
                    "name": reference_image_id,
                    "imageInputType": "IMAGE_INPUT_TYPE_REFERENCE"
                }]
            
            body = {
                "requests": [request_data]
            }
            
            url = GENERATE_IMAGE_URL_TEMPLATE.format(project_id=project_id)
            
            headers = {
                "accept": "*/*",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "authorization": f"Bearer {access_token}",
                "cache-control": "no-cache",
                "content-type": "text/plain;charset=UTF-8",
                "pragma": "no-cache",
                "Referer": "https://labs.google/"
            }
            
            response = await asyncio.to_thread(
                curl_requests.post,
                url,
                headers=headers,
                data=orjson.dumps(body),
                impersonate=BROWSER,
                timeout=TIMEOUT
            )
            
            if response.status_code != 200:
                raise GrokApiException(
                    f"生成图片失败: {response.status_code}",
                    "HTTP_ERROR",
                    {"status": response.status_code}
                )
            
            data = response.json()
            logger.debug("[Flow] 图片生成成功")
            return data
            
        except curl_requests.RequestsError as e:
            logger.error(f"[Flow] 网络错误: {e}")
            raise GrokApiException(f"网络错误: {e}", "NETWORK_ERROR") from e
        except Exception as e:
            logger.error(f"[Flow] 生成图片失败: {e}")
            raise GrokApiException(f"生成图片失败: {e}", "REQUEST_ERROR") from e

