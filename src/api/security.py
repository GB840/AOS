import logging
import secrets
import bcrypt
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from utils.config import config

logger = logging.getLogger(__name__)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """
    HTTPS强制重定向中间件
    
    在生产环境强制使用HTTPS，将HTTP请求重定向到HTTPS
    """
    
    def __init__(self, app, https_port: int = 443):
        super().__init__(app)
        self.https_port = https_port
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # 检查是否已经是HTTPS
        if request.url.scheme == "https":
            return await call_next(request)
        
        # 在生产环境强制重定向到HTTPS
        if config.APP_ENV == "production":
            # 构建HTTPS URL
            https_url = request.url.replace(
                scheme="https",
                netloc=f"{request.url.hostname}:{self.https_port}" if self.https_port != 443 else request.url.hostname
            )
            
            logger.warning(f"HTTP请求重定向到HTTPS: {request.url} -> {https_url}")
            return Response(
                status_code=301,
                headers={"Location": str(https_url)}
            )
        
        # 开发环境允许HTTP
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    安全HTTP头中间件
    
    添加各种安全相关的HTTP头，包括HSTS、CSP等
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # HSTS (HTTP Strict Transport Security)
        if config.APP_ENV == "production":
            # 生产环境：1年HSTS，包含子域名
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        else:
            # 开发环境：较短时间，便于测试
            response.headers["Strict-Transport-Security"] = "max-age=300"
        
        # 防止点击劫持
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        
        # 防止MIME类型嗅探
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # XSS保护
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # 引用策略
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # 权限策略
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
        return response


def generate_api_key() -> str:
    """生成安全的API密钥"""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    """对API密钥进行哈希处理"""
    if isinstance(api_key, str):
        api_key = api_key.encode('utf-8')
    return bcrypt.hashpw(api_key, bcrypt.gensalt()).decode('utf-8')


def verify_api_key_hash(api_key: str, hashed_key: str) -> bool:
    """验证API密钥哈希"""
    try:
        if isinstance(api_key, str):
            api_key = api_key.encode('utf-8')
        if isinstance(hashed_key, str):
            hashed_key = hashed_key.encode('utf-8')
        return bcrypt.checkpw(api_key, hashed_key)
    except Exception as e:
        logger.error(f"API密钥验证失败: {e}")
        return False


# ===== OAuth2 / JWT (团队级认证 seam：与 API-Key 并存) =====
# 个人级用 API-Key；团队/公司级可无缝切换为 OAuth2/JWT，调用方接口不变。
def _import_jwt():
    import jwt  # PyJWT
    return jwt


def create_access_token(subject: str, expires_min: Optional[int] = None) -> str:
    """签发 JWT (HS256). 团队级多用户/SSO 接入时换实现(如 RS256/OIDC)即可。"""
    jwt = _import_jwt()
    now = datetime.now()
    exp = now + timedelta(minutes=expires_min or config.AUTH_JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, config.AUTH_JWT_SECRET, algorithm=config.AUTH_JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """校验 JWT，返回 subject；无效/过期返回 None。"""
    try:
        jwt = _import_jwt()
        payload = jwt.decode(token, config.AUTH_JWT_SECRET, algorithms=[config.AUTH_JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def authenticate_user(username: str, password: str) -> bool:
    """校验用户凭据（团队级可替换为 DB/OIDC/LDAP，接口不变）。"""
    return username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD


async def get_api_key(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query),
) -> str:
    """验证API密钥（支持明文和哈希比较）"""
    api_key = api_key_header or api_key_query
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is required",
            headers={"WWW-Authenticate": f"Bearer realm='AOS API'"},
        )
    
    # 支持明文比较（向后兼容）
    if api_key == config.API_KEY:
        logger.warning("使用明文API密钥比较，建议升级到哈希验证")
        return api_key
    
    # 支持哈希比较（如果配置了哈希值）
    if hasattr(config, 'API_KEY_HASH') and config.API_KEY_HASH:
        if verify_api_key_hash(api_key, config.API_KEY_HASH):
            return api_key
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key",
        headers={"WWW-Authenticate": f"Bearer realm='AOS API'"},
    )


class APISecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 统一网关收编的子路径（/web、/openclaw、/deerflow）由各自上游自带鉴权，
        # 不走 AOS 的 API-Key 校验，否则浏览器/Streamlit 会被 401 挡在门外。
        if any(path == p or path.startswith(p + "/") for p in ("/web", "/openclaw", "/deerflow")):
            return await call_next(request)

        if path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json"):
            return await call_next(request)

        if path == "/" or path.endswith("/health") or path.endswith("/health/deep") or path == "/api/auth/token":
            return await call_next(request)

        # 工具型只读/刷新端点（技能目录本就经 DeerFlow 网关公开，无敏感写操作）
        if path == "/api/skills/deerflow" or path == "/api/skills/refresh":
            return await call_next(request)

        # 1) 团队级: OAuth2/JWT Bearer（与 API-Key 并存）
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            sub = decode_access_token(auth[7:].strip())
            if sub:
                return await call_next(request)
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized", "detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 2) 个人级: 静态 API-Key
        if config.API_KEY:
            api_key = request.headers.get(API_KEY_NAME) or request.query_params.get(API_KEY_NAME)
            if api_key != config.API_KEY:
                logger.warning(f"Unauthorized access attempt to {path} from {request.client.host}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": "Unauthorized", "detail": "Invalid or missing API Key / Bearer token"},
                )

        response = await call_next(request)
        return response


from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    改进的速率限制中间件 - 修复内存泄漏
    
    使用滑动窗口算法 + 定期清理过期条目，防止内存泄漏
    """
    
    def __init__(self, app, max_requests: int = 100, time_window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.time_window = time_window_seconds
        
        # 使用线程安全的数据结构
        self._clients = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(minutes=5)  # 每5分钟清理一次
        
        logger.info(f"速率限制中间件初始化: {max_requests}请求/{time_window_seconds}秒")
    
    def _cleanup_expired_clients(self):
        """清理过期的客户端记录，防止内存泄漏"""
        now = datetime.now()
        
        # 检查是否需要清理
        if now - self._last_cleanup < self._cleanup_interval:
            return
        
        with self._lock:
            expired_clients = []
            
            # 找出所有过期的客户端
            for client_ip, requests in self._clients.items():
                # 移除超出时间窗口的请求
                while requests and now - requests[0] > timedelta(seconds=self.time_window):
                    requests.popleft()
                
                # 如果客户端没有活跃请求，标记为过期
                if not requests:
                    expired_clients.append(client_ip)
            
            # 删除过期的客户端记录
            for client_ip in expired_clients:
                del self._clients[client_ip]
            
            self._last_cleanup = now
            
            if expired_clients:
                logger.info(f"清理了 {len(expired_clients)} 个过期的客户端记录")

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now()
        
        # 定期清理过期记录
        self._cleanup_expired_clients()
        
        # ⚠️ 关键并发正确性: threading.Lock 只保护限流簿记 (deque 读写),
        # 绝不能跨 `await call_next(request)` 持锁。此前把 await 放在 with 块内,
        # 单 worker uvicorn 下会死锁: 请求A持锁 await 长耗时 brain.chat 期间,
        # 请求B(如 /health 轮询)进入 dispatch 执行 `with self._lock` 会同步阻塞
        # 事件循环线程 -> 事件循环无法回去跑A的续体释放锁 -> 全进程冻结。
        # 修法: 锁内只做记账并算出 remaining, await 在锁外执行。
        with self._lock:
            client_requests = self._clients[client_ip]

            # 移除超出时间窗口的旧请求
            while client_requests and now - client_requests[0] > timedelta(seconds=self.time_window):
                client_requests.popleft()

            # 检查是否超限
            if len(client_requests) >= self.max_requests:
                logger.warning(f"速率限制超限: {client_ip} ({len(client_requests)}/{self.max_requests})")
                reset = int((now - client_requests[0]).total_seconds()) if client_requests else self.time_window
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={
                        "Retry-After": str(self.time_window),
                        "X-RateLimit-Limit": str(self.max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                    },
                    content={
                        "error": "Too Many Requests",
                        "detail": f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.time_window} seconds.",
                        "retry_after": self.time_window,
                    }
                )

            # 记录新请求
            client_requests.append(now)
            remaining = self.max_requests - len(client_requests)

        # await 必须在锁外, 避免跨 await 持锁导致事件循环死锁
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response