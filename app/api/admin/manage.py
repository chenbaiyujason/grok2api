"""管理接口 - 系统配置"""

import secrets
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.config import setting
from app.core.logger import logger
from app.services.flow.client import FlowClient
from app.core.exception import GrokApiException


router = APIRouter(tags=["管理"])

# 常量
STATIC_DIR = Path(__file__).parents[2] / "template"
SESSION_EXPIRE_HOURS = 24

# 会话存储
_sessions: Dict[str, datetime] = {}


# === 请求/响应模型 ===

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    token: Optional[str] = None
    message: str


class UpdateSettingsRequest(BaseModel):
    global_config: Optional[Dict[str, Any]] = None
    flow_config: Optional[Dict[str, Any]] = None


# === 辅助函数 ===

def verify_admin_session(authorization: Optional[str] = Header(None)) -> bool:
    """验证管理员会话"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"error": "未授权访问", "code": "UNAUTHORIZED"})
    
    token = authorization[7:]
    
    if token not in _sessions:
        raise HTTPException(status_code=401, detail={"error": "会话无效", "code": "SESSION_INVALID"})
    
    if datetime.now() > _sessions[token]:
        del _sessions[token]
        raise HTTPException(status_code=401, detail={"error": "会话已过期", "code": "SESSION_EXPIRED"})
    
    return True


# === 页面路由 ===

@router.get("/login", response_class=HTMLResponse)
async def login_page():
    """登录页面"""
    login_html = STATIC_DIR / "login.html"
    if login_html.exists():
        return login_html.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail="登录页面不存在")


@router.get("/manage", response_class=HTMLResponse)
async def manage_page():
    """管理页面"""
    admin_html = STATIC_DIR / "admin.html"
    if admin_html.exists():
        return admin_html.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail="管理页面不存在")


# === API端点 ===

@router.post("/api/login", response_model=LoginResponse)
async def admin_login(request: LoginRequest) -> LoginResponse:
    """管理员登录"""
    try:
        logger.debug(f"[Admin] 登录尝试: {request.username}")

        expected_user = setting.global_config.get("admin_username", "")
        expected_pass = setting.global_config.get("admin_password", "")

        if request.username != expected_user or request.password != expected_pass:
            logger.warning(f"[Admin] 登录失败: {request.username}")
            return LoginResponse(success=False, message="用户名或密码错误")

        session_token = secrets.token_urlsafe(32)
        _sessions[session_token] = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)

        logger.debug(f"[Admin] 登录成功: {request.username}")
        return LoginResponse(success=True, token=session_token, message="登录成功")

    except Exception as e:
        logger.error(f"[Admin] 登录异常: {e}")
        raise HTTPException(status_code=500, detail={"error": f"登录失败: {e}", "code": "LOGIN_ERROR"})


@router.post("/api/logout")
async def admin_logout(_: bool = Depends(verify_admin_session), authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """管理员登出"""
    try:
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:]
            if token in _sessions:
                del _sessions[token]
                logger.debug("[Admin] 登出成功")
                return {"success": True, "message": "登出成功"}

        logger.warning("[Admin] 登出失败: 无效会话")
        return {"success": False, "message": "无效的会话"}

    except Exception as e:
        logger.error(f"[Admin] 登出异常: {e}")
        raise HTTPException(status_code=500, detail={"error": f"登出失败: {e}", "code": "LOGOUT_ERROR"})


@router.get("/api/settings")
async def get_settings(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取配置"""
    try:
        logger.debug("[Admin] 获取配置")
        return {"success": True, "data": {"global": setting.global_config, "flow": setting.flow_config}}
    except Exception as e:
        logger.error(f"[Admin] 获取配置失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取失败: {e}", "code": "GET_SETTINGS_ERROR"})


@router.post("/api/settings")
async def update_settings(request: UpdateSettingsRequest, _: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """更新配置"""
    try:
        logger.debug("[Admin] 更新配置")
        await setting.save(global_config=request.global_config, flow_config=request.flow_config)
        logger.debug("[Admin] 配置更新成功")
        return {"success": True, "message": "配置更新成功"}
    except Exception as e:
        logger.error(f"[Admin] 更新配置失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"更新失败: {e}", "code": "UPDATE_SETTINGS_ERROR"})


@router.get("/api/credits")
async def get_credits(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取余额信息（管理后台专用）"""
    try:
        logger.debug("[Admin] 查询余额")
        
        # 获取 session_token
        session_token = setting.get_session_token()
        if not session_token:
            return {
                "success": False,
                "message": "Session token 未配置",
                "credits": 0,
                "user_paygate_tier": ""
            }
        
        # 获取 access_token
        access_token = await FlowClient.get_access_token(session_token)
        
        # 获取余额
        credits_data = await FlowClient.get_credits(access_token)
        
        return {
            "success": True,
            "credits": credits_data.get("credits", 0),
            "user_paygate_tier": credits_data.get("userPaygateTier", "")
        }
        
    except GrokApiException as e:
        logger.error(f"[Admin] 查询余额失败: {e}")
        return {
            "success": False,
            "message": str(e),
            "credits": 0,
            "user_paygate_tier": ""
        }
    except Exception as e:
        logger.error(f"[Admin] 查询余额异常: {e}")
        return {
            "success": False,
            "message": f"查询余额失败: {e}",
            "credits": 0,
            "user_paygate_tier": ""
        }
