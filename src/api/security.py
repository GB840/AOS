import logging
import secrets
import hmac
import bcrypt
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from utils.config import config
from utils.keystore import load_jwt_keys
from pathlib import Path

logger = logging.getLogger(__name__)

# JWT 非对称密钥 (RS256) 缓存：首次使用时解析，避免每次请求重复读盘。
_jwt_key_cache: tuple[str, str] | None = None


def _get_jwt_keys() -> tuple[str, str]:
    """返回 (private_pem, public_pem)，用于 RS256 签名/验签。"""
    global _jwt_key_cache
    if _jwt_key_cache is None:
        _jwt_key_cache = load_jwt_keys(base_dir=Path(config.BASE_DIR), app_env=config.APP_ENV)
    return _jwt_key_cache

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_NAME, auto_error=False)


class HTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """生产环境强制 HTTPS（经反向代理终止 TLS 时也能正确判定）。"""

    def __init__(self, app, https_port: int = 443):
        super().__init__(app)
        self.https_port = https_port

    @staticmethod
    def _is_https(request: Request) -> bool:
        # 反向代理（nginx 等）终止 TLS 后，原始协议经 X-Forwarded-Proto/Scheme 透传；
        # 否则 request.url.scheme 永远是 http，会导致误判/重定向环。
        fwd = (request.headers.get("X-Forwarded-Proto") or request.headers.get("X-Forwarded-Scheme") or "").lower()
        return fwd == "https" or request.url.scheme == "https"

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._is_https(request):
            return await call_next(request)

        if config.APP_ENV == "production":
            https_url = request.url.replace(
                scheme="https",
                netloc=f"{request.url.hostname}:{self.https_port}" if self.https_port != 443 else request.url.hostname,
            )
            logger.warning("HTTP 请求重定向到 HTTPS: %s -> %s", request.url, https_url)
            return Response(status_code=301, headers={"Location": str(https_url)})

        # 开发环境允许 HTTP
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
        
        # 防止点击劫持和XSS攻击
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self';"
        )
        
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
    """使用恒定时间验证API密钥哈希，防止时序攻击"""
    try:
        # 输入验证
        if not api_key or not hashed_key:
            return False
            
        # 验证哈希格式 (bcrypt哈希应该以$2b$开头且长度为60)
        if not hashed_key.startswith('$2b$') or len(hashed_key) != 60:
            logger.warning("API密钥哈希格式无效")
            return False
        
        # 编码处理
        if isinstance(api_key, str):
            api_key_bytes = api_key.encode('utf-8')
        else:
            api_key_bytes = api_key
        if isinstance(hashed_key, str):
            hashed_key_bytes = hashed_key.encode('utf-8')
        else:
            hashed_key_bytes = hashed_key
            
        # 使用bcrypt恒定时间比较
        return bcrypt.checkpw(api_key_bytes, hashed_key_bytes)
    except Exception as e:
        # 即使发生异常也要执行虚假比较维持时序恒定
        try:
            # 执行虚假比较防止时序信息泄露
            bcrypt.checkpw(b"fake_key", b"$2b$12$fake_hash_for_constant_time_protection")
        except Exception as e:
            logger.warning("虚假 bcrypt 恒定时间比较失败: %s", e)
        logger.error(f"API密钥验证异常(已防止时序泄露): {type(e).__name__}")
        return False


# ===== OAuth2 / JWT (团队级认证 seam：与 API-Key 并存) =====
# 个人级用 API-Key；团队/公司级可无缝切换为 OAuth2/JWT，调用方接口不变。
def _import_jwt():
    import jwt  # PyJWT
    return jwt


def create_access_token(subject: str, expires_min: Optional[int] = None) -> str:
    """签发 JWT (RS256, 私钥签名). 团队级多用户/SSO 接入时仅换密钥管理即可。"""
    jwt = _import_jwt()
    private_pem, _public_pem = _get_jwt_keys()
    now = datetime.now()
    exp = now + timedelta(minutes=expires_min or config.AUTH_JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, private_pem, algorithm=config.AUTH_JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """校验 JWT，返回 subject；无效/过期返回 None。"""
    try:
        jwt = _import_jwt()
        _private_pem, public_pem = _get_jwt_keys()
        payload = jwt.decode(token, public_pem, algorithms=[config.AUTH_JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None


def authenticate_user(username: str, password: str) -> bool:
    """校验用户凭据（恒定时间比较，避免计时侧信道）。团队级可替换为 DB/OIDC/LDAP。"""
    import hmac

    user_ok = hmac.compare_digest(username or "", config.ADMIN_USERNAME or "")
    pass_ok = hmac.compare_digest(password or "", config.ADMIN_PASSWORD or "")
    return user_ok and pass_ok


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
            headers={"WWW-Authenticate": "Bearer realm='AOS API'"},
        )
    
    # 安全升级：已移除明文API密钥支持，强制使用哈希验证
    
    # 强制哈希比较（安全升级）
    if hasattr(config, 'API_KEY_HASH') and config.API_KEY_HASH:
        if verify_api_key_hash(api_key, config.API_KEY_HASH):
            return api_key
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API Key. Please ensure you are using a hashed API key configuration",
        headers={"WWW-Authenticate": "Bearer realm='AOS API'"},
    )


class APISecurityMiddleware(BaseHTTPMiddleware):
    # 统一网关收编的上游子路径：各自上游自带鉴权（/web=Streamlit 控制台、
    # /openclaw=OpenClaw 网关、/deerflow=DeerFlow 网关），注意：AOS仅做流量转发，
    # 不处理上游网关的实际权限控制。
    _UPSTREAM_PREFIXES = ("/web", "/openclaw", "/deerflow")
    
    def __init__(self, app, require_upstream_auth_check: bool = None):
        """增强安全性：可选择是否要求上游认证检查
        
        Args:
            app: FastAPI应用
            require_upstream_auth_check: 是否强制验证上游认证头
                       默认为None时，生产环境自动启用严格模式
        """
        super().__init__(app)

        # 安全默认值：生产环境自动启用严格模式
        if require_upstream_auth_check is None:
            from utils.config import config
            self.require_upstream_auth_check = config.APP_ENV == "production"
        else:
            self.require_upstream_auth_check = require_upstream_auth_check

        # 凭据铁律：生产环境必须至少配置 API_KEY 或 API_KEY_HASH 其一，否则 fail-fast。
        # 旧逻辑仅查 API_KEY，运维按推荐只配哈希口令(API_KEY_HASH)时反而跳过鉴权 -> 匿名可访问。
        if config.APP_ENV == "production" and not (config.API_KEY or getattr(config, "API_KEY_HASH", None)):
            raise RuntimeError(
                "安全配置缺失：生产环境必须设置 AOS_API_KEY 或 AOS_API_KEY_HASH 之一，"
                "否则任何人都可匿名访问。已按凭据铁律 fail-fast 拒绝启动。"
            )
        # 是否启用统一鉴权：未配置任何凭据时（仅开发环境，生产已在上方 fail-fast）放开。
        self._auth_enabled = bool(config.API_KEY or getattr(config, "API_KEY_HASH", None))

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # 1) 永远公开：根路径 + 健康探针（供 supervisor/负载均衡探活）
        #    + 登录入口 /api/auth/token（换取 JWT，不可能要求先认证）。
        if path == "/" or path.endswith("/health") or path.endswith("/health/deep") or path == "/api/auth/token":
            return await call_next(request)

        # 2) 上游网关子路径：由各自上游鉴权（架构性豁免，非弱鉴权）。
        is_upstream = any(path == p or path.startswith(p + "/") for p in self._UPSTREAM_PREFIXES)
        if is_upstream:
            # 安全增强：检查上游认证头是否被篡改
            if self.require_upstream_auth_check and not self._validate_upstream_auth(request):
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"error": "Unauthorized", "detail": "Invalid upstream authentication"},
                )
            return await call_next(request)

        # 3) API 文档与 OpenAPI Schema：
        #    开发环境放开便于本地调试；生产环境禁止匿名浏览接口面，必须走下方统一鉴权。
        is_docs = path.startswith("/docs") or path.startswith("/redoc") or path.startswith("/openapi.json")
        if is_docs and config.APP_ENV != "production":
            return await call_next(request)

        # 4) 技能目录/刷新端点（原 G4 免认证豁免已收回）：始终要求认证，
        #    禁止匿名获取内部能力清单或触发服务端重索引。落入下方统一鉴权。

        # 5) 统一鉴权：团队级 Bearer(JWT) 或个人级静态 API-Key（明文 + 哈希均支持）
        #    未配置任何凭据时（仅开发环境，已在前置 fail-fast 排除生产）放开。
        if not self._auth_enabled:
            return await call_next(request)

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

        # 个人级: 静态 API-Key（恒定时间比较，支持明文 + bcrypt 哈希，避免计时侧信道）
        api_key = request.headers.get(API_KEY_NAME) or request.query_params.get(API_KEY_NAME)
        if not self._check_api_key(api_key or ""):
            # 审计日志仅记录脱敏后的密钥前缀 (可溯源但不泄露), 不记录完整密钥。
            from utils.sanitize import mask_secret
            logger.warning(
                "Unauthorized access attempt to %s from %s key=%s",
                path, request.client.host, mask_secret(api_key or ""),
            )
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized", "detail": "Invalid or missing API Key / Bearer token"},
            )

        response = await call_next(request)
        return response
    
    def _check_api_key(self, api_key: str) -> bool:
        """恒定时间校验 API Key：支持明文(API_KEY) 与 bcrypt 哈希(API_KEY_HASH) 任一。"""
        if not api_key:
            return False
        if config.API_KEY and hmac.compare_digest(api_key, config.API_KEY):
            return True
        api_key_hash = getattr(config, "API_KEY_HASH", None)
        if api_key_hash and verify_api_key_hash(api_key, api_key_hash):
            return True
        return False

    def _validate_upstream_auth(self, request: Request) -> bool:
        """验证上游网关请求确实携带有效的 AOS 凭据（而非仅存在任意头，旧逻辑可被伪造头绕过）。

        旧实现：只要请求带任意 Authorization 头即返回 True -> 伪造头可过上游校验。
        新实现：必须能通过 API-Key(明文/哈希) 或 JWT 或网关共享令牌中的至少一种。
        """
        # 个人级 API-Key（明文 + 哈希，恒定时间）
        api_key = request.headers.get(API_KEY_NAME) or request.query_params.get(API_KEY_NAME)
        if self._check_api_key(api_key or ""):
            return True

        # 团队级 Bearer(JWT)
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            if decode_access_token(auth[7:].strip()):
                return True

        # 网关间共享令牌（如配置了 UPSTREAM_TOKEN），恒定时间比较
        tok = request.headers.get("X-Upstream-Token")
        upstream_token = getattr(config, "UPSTREAM_TOKEN", None)
        if tok and upstream_token and hmac.compare_digest(tok, upstream_token):
            return True

        return False


from datetime import datetime, timedelta
from collections import defaultdict, deque
import threading

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    改进的速率限制中间件 - 修复内存泄漏 + v1.0 API Key 治理。

    使用滑动窗口算法 + 定期清理过期条目，防止内存泄漏。
    同时支持 IP 级别和 API Key 级别的限流。
    """

    def __init__(self, app, max_requests: int = 100, time_window_seconds: int = 60):
        super().__init__(app)
        self.max_requests = max_requests
        self.time_window = time_window_seconds
        # API Key 所有者可享受更高限额
        self.api_key_max_requests = max_requests * 3  # 认证用户 3x 限额

        # 使用线程安全的数据结构
        self._clients: dict = defaultdict(deque)
        self._api_keys: dict = defaultdict(deque)  # v1.0: API Key 级别限流
        self._lock = threading.Lock()
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(minutes=5)

        logger.info("速率限制中间件: IP=%dreq/%ds | API-Key=%dreq/%ds",
                    max_requests, time_window_seconds,
                    self.api_key_max_requests, time_window_seconds)

    def _cleanup_expired_clients(self):
        """清理过期的客户端记录，防止内存泄漏"""
        now = datetime.now()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        with self._lock:
            for store in (self._clients, self._api_keys):
                expired = []
                for key, requests in store.items():
                    while requests and now - requests[0] > timedelta(seconds=self.time_window):
                        requests.popleft()
                    if not requests:
                        expired.append(key)
                for key in expired:
                    del store[key]
            self._last_cleanup = now
            if expired:
                logger.debug("限流清理: %d 条过期记录", len(expired))

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = datetime.now()

        self._cleanup_expired_clients()

        # v1.0: 优先 API Key 限流，再 IP 限流
        api_key = request.headers.get("X-API-Key", "") or request.headers.get("Authorization", "")
        if api_key.startswith("Bearer "):
            api_key = api_key[7:]
        use_api_key = bool(api_key and len(api_key) > 16)

        with self._lock:
            if use_api_key:
                store = self._api_keys
                key = api_key[:32]  # 截断保护隐私
                limit = self.api_key_max_requests
            else:
                store = self._clients
                key = client_ip
                limit = self.max_requests

            requests_deque = store[key]
            while requests_deque and now - requests_deque[0] > timedelta(seconds=self.time_window):
                requests_deque.popleft()

            if len(requests_deque) >= limit:
                logger.warning("速率限制: %s (%d/%d)", key, len(requests_deque), limit)
                reset = int((now - requests_deque[0]).total_seconds()) if requests_deque else self.time_window
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    headers={
                        "Retry-After": str(self.time_window),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(reset),
                    },
                    content={
                        "error": "Too Many Requests",
                        "detail": f"Rate limit exceeded ({limit}/{self.time_window}s).",
                        "retry_after": self.time_window,
                    }
                )

            requests_deque.append(now)
            remaining = limit - len(requests_deque)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response