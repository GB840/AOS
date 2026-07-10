"""
统一异常处理系统

提供标准化的异常定义、处理和日志记录
"""

import logging
import traceback
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorCode(str, Enum):
    """标准错误码"""
    
    # 通用错误 (1xxx)
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    
    # 认证授权错误 (2xxx)
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INVALID_API_KEY = "INVALID_API_KEY"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    
    # 数据库错误 (3xxx)
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    DATABASE_QUERY_ERROR = "DATABASE_QUERY_ERROR"
    
    # 资源错误 (4xxx)
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    RESOURCE_ALREADY_EXISTS = "RESOURCE_ALREADY_EXISTS"
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    
    # AI模型错误 (5xxx)
    MODEL_ERROR = "MODEL_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    EMBEDDING_ERROR = "EMBEDDING_ERROR"
    LLM_ERROR = "LLM_ERROR"
    
    # 配置错误 (6xxx)
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    MISSING_REQUIRED_CONFIG = "MISSING_REQUIRED_CONFIG"
    
    # 文件处理错误 (7xxx)
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_UPLOAD_ERROR = "FILE_UPLOAD_ERROR"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    FILE_SIZE_EXCEEDED = "FILE_SIZE_EXCEEDED"


class AOSException(Exception):
    """
    AOS基础异常类
    
    所有自定义异常都应该继承这个类
    """
    
    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        self.timestamp = datetime.now().isoformat()
        
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "status_code": self.status_code,
            "timestamp": self.timestamp,
            "details": self.details
        }
    
    def to_http_exception(self) -> HTTPException:
        """转换为FastAPI HTTP异常"""
        return HTTPException(
            status_code=self.status_code,
            detail=self.to_dict()
        )


# 具体异常类
class AuthenticationException(AOSException):
    """认证异常"""
    
    def __init__(self, message: str = "认证失败", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.UNAUTHORIZED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details
        )


class AuthorizationException(AOSException):
    """授权异常"""
    
    def __init__(self, message: str = "权限不足", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details
        )


class ResourceNotFoundException(AOSException):
    """资源未找到异常"""
    
    def __init__(self, resource_type: str, resource_id: str, details: Optional[Dict[str, Any]] = None):
        message = f"{resource_type} '{resource_id}' 不存在"
        super().__init__(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details
        )


class DatabaseException(AOSException):
    """数据库异常"""
    
    def __init__(self, message: str = "数据库错误", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class ModelException(AOSException):
    """AI模型异常"""
    
    def __init__(self, message: str = "模型错误", model_name: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        message = f"模型错误: {message}"
        if model_name:
            message = f"{model_name}: {message}"
        
        super().__init__(
            message=message,
            error_code=ErrorCode.MODEL_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class ConfigurationException(AOSException):
    """配置异常"""
    
    def __init__(self, message: str = "配置错误", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CONFIGURATION_ERROR,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details
        )


class FileUploadException(AOSException):
    """文件上传异常"""
    
    def __init__(self, message: str = "文件上传错误", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.FILE_UPLOAD_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details
        )


class ValidationError(AOSException):
    """数据验证异常"""
    
    def __init__(self, message: str = "数据验证失败", field_errors: Optional[Dict[str, str]] = None, details: Optional[Dict[str, Any]] = None):
        if field_errors:
            details = details or {}
            details["field_errors"] = field_errors
        
        super().__init__(
            message=message,
            error_code=ErrorCode.INVALID_REQUEST,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class ErrorResponse(BaseModel):
    """标准错误响应模型"""
    error_code: str = Field(..., description="错误码")
    message: str = Field(..., description="错误消息")
    status_code: int = Field(..., description="HTTP状态码")
    timestamp: str = Field(..., description="错误时间戳")
    details: Dict[str, Any] = Field(default_factory=dict, description="错误详情")
    request_id: Optional[str] = Field(None, description="请求ID")


async def aos_exception_handler(request: Request, exc: AOSException) -> JSONResponse:
    """
    AOS自定义异常处理器
    
    统一处理所有AOSException及其子类异常
    """
    # 生成请求ID
    request_id = getattr(request.state, 'request_id', None)
    
    # 记录错误日志
    logger.error(
        f"AOS异常处理: {exc.error_code.value} - {exc.message}",
        extra={
            "error_code": exc.error_code.value,
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details
        }
    )
    
    # 构建错误响应
    error_response = ErrorResponse(
        error_code=exc.error_code.value,
        message=exc.message,
        status_code=exc.status_code,
        timestamp=exc.timestamp,
        details=exc.details,
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    通用异常处理器
    
    处理所有未被特定处理器捕获的异常
    """
    # 生成请求ID
    request_id = getattr(request.state, 'request_id', None)
    
    # 获取完整的堆栈跟踪
    stack_trace = traceback.format_exc()
    
    # 记录错误日志（包含堆栈跟踪）
    logger.error(
        f"未处理的异常: {type(exc).__name__} - {str(exc)}",
        extra={
            "error_type": type(exc).__name__,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "stack_trace": stack_trace
        }
    )
    
    # 构建用户友好的错误消息（不暴露敏感信息）
    user_message = "服务器内部错误，请稍后重试"
    if config.DEBUG:
        # 开发环境显示详细错误
        user_message = f"{type(exc).__name__}: {str(exc)}"
    
    # 构建错误响应
    error_response = ErrorResponse(
        error_code=ErrorCode.INTERNAL_ERROR.value,
        message=user_message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        timestamp=datetime.now().isoformat(),
        details={
            "error_type": type(exc).__name__,
            "debug_mode": config.DEBUG
        } if config.DEBUG else {},
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response.dict()
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    FastAPI HTTP异常处理器
    
    处理FastAPI内置的HTTPException
    """
    # 生成请求ID
    request_id = getattr(request.state, 'request_id', None)
    
    # 记录警告日志
    logger.warning(
        f"HTTP异常: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method
        }
    )
    
    # 构建错误响应
    error_response = ErrorResponse(
        error_code=str(exc.status_code),
        message=str(exc.detail),
        status_code=exc.status_code,
        timestamp=datetime.now().isoformat(),
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.dict()
    )


def setup_exception_handlers(app):
    """
    设置所有异常处理器
    
    Args:
        app: FastAPI应用实例
    """
    # 注册AOS自定义异常处理器
    app.add_exception_handler(AOSException, aos_exception_handler)
    
    # 注册通用异常处理器
    app.add_exception_handler(Exception, general_exception_handler)
    
    # 注册HTTP异常处理器
    app.add_exception_handler(HTTPException, http_exception_handler)
    
    logger.info("异常处理器注册完成")


def handle_errors(logger_instance: Optional[logging.Logger] = None, reraise: bool = False):
    """
    错误处理装饰器
    
    使用示例：
        @handle_errors()
        def risky_function():
            # 可能出错的代码
            pass
    """
    if logger_instance is None:
        logger_instance = logger
    
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except AOSException as e:
                # 已知的AOS异常，重新抛出
                logger_instance.error(f"AOS异常在 {func.__name__}: {e.message}")
                if reraise:
                    raise
                return {"error": e.message, "error_code": e.error_code.value}
            except Exception as e:
                # 未知异常，记录并转换为AOS异常
                logger_instance.error(f"未预期的异常在 {func.__name__}: {str(e)}")
                aos_exc = AOSException(
                    message=f"操作失败: {str(e)}",
                    error_code=ErrorCode.INTERNAL_ERROR
                )
                if reraise:
                    raise aos_exc
                return {"error": aos_exc.message, "error_code": aos_exc.error_code.value}
        
        return wrapper
    return decorator


# 导入配置（避免循环导入）
try:
    from utils.config import config
except ImportError:
    # 如果导入失败，使用默认配置
    class DefaultConfig:
        DEBUG = False
    config = DefaultConfig()