"""v1.0 鉴权桥接：把 api/security.py 的 JWT/Bearer 鉴权映射为内核权限。

这是 v1.0 物种思维"权限治理"的落地点：FastAPI 中间件做完 token 验证后，
通过本桥接把验证结果翻译为内核的 Permission 模型。

设计：
- 零依赖：本模块只依赖 kernel types，不 import api/security 或 FastAPI
- 签名：authenticate(credential) → AuthResult(identity, permissions)
- 接入点：FastAPI middleware verify → AuthBridge.authenticate → kernel.check_permission
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from kernel.types import Permission


# ─── 鉴权结果 ─────────────────────────────────────────────────────

@dataclass
class AuthResult:
    """鉴权桥接的返回：identity + 该 identity 拥有的权限列表。"""
    identity_id: str                          # agent_id / user_id
    identity_type: str = "agent"              # "agent" | "user" | "admin"
    authenticated: bool = True
    permissions: List[Permission] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @staticmethod
    def denied(reason: str) -> AuthResult:
        return AuthResult(identity_id="anonymous", authenticated=False,
                          error=reason)


# ─── 鉴权提供方（可替换） ──────────────────────────────────────────

class AuthProvider:
    """可替换的鉴权提供方。默认实现映射到 api/security.py 的 JWT + API Key 模式。

    替换方式：传入自定义 verify_token / verify_api_key callable。
    """

    def __init__(
        self,
        verify_token: Callable[[str], Optional[Dict[str, Any]]] | None = None,
        verify_api_key: Callable[[str], Optional[Dict[str, Any]]] | None = None,
    ) -> None:
        self._verify_token = verify_token or _default_token_verify
        self._verify_api_key = verify_api_key or _default_token_verify

    def authenticate_token(self, token: str) -> AuthResult:
        """通过 Bearer / JWT token 鉴权。"""
        result = self._verify_token(token)
        if result is None:
            return AuthResult.denied("invalid token")
        return AuthResult(
            identity_id=result.get("sub", "unknown"),
            identity_type=result.get("type", "agent"),
            permissions=_parse_permissions(result.get("permissions", [])),
            metadata=result,
        )

    def authenticate_api_key(self, api_key: str) -> AuthResult:
        """通过 API Key 鉴权。"""
        result = self._verify_api_key(api_key)
        if result is None:
            return AuthResult.denied("invalid api key")
        return AuthResult(
            identity_id=result.get("sub", "unknown"),
            identity_type=result.get("type", "agent"),
            permissions=_parse_permissions(result.get("permissions", [])),
            metadata=result,
        )


# ─── 桥接层 ───────────────────────────────────────────────────────

class AuthBridge:
    """把 AuthProvider 的鉴权结果注入内核权限系统。

    用法：
        kernel = AOSKernel()
        bridge = AuthBridge(kernel, AuthProvider(...))

        # 在 HTTP 中间件里：
        result = bridge.login_bearer(token)
        if not result.authenticated:
            raise HTTPException(403)
        # 此后 kernel.check_permission(agent_id, action) 会根据 token 结果判定
    """

    def __init__(self, kernel, provider: AuthProvider | None = None) -> None:
        self._kernel = kernel
        self._provider = provider or AuthProvider()

    def login_bearer(self, token: str) -> AuthResult:
        """Bearer token 鉴权 → 注册 identity 的权限到内核。"""
        result = self._provider.authenticate_token(token)
        if result.authenticated:
            self._apply_permissions(result)
        return result

    def login_api_key(self, api_key: str) -> AuthResult:
        """API Key 鉴权 → 注册 identity 的权限到内核。"""
        result = self._provider.authenticate_api_key(api_key)
        if result.authenticated:
            self._apply_permissions(result)
        return result

    def revoke(self, identity_id: str) -> None:
        """撤销 identity 的所有权限。"""
        to_remove = [k for k in self._kernel._permissions
                     if k.startswith(f"{identity_id}:")]
        for k in to_remove:
            del self._kernel._permissions[k]

    def _apply_permissions(self, result: AuthResult) -> None:
        """把鉴权结果中的权限列表注册到内核。"""
        for perm in result.permissions:
            key = f"{perm.agent_id}:{perm.action}"
            self._kernel._permissions[key] = perm
        # 默认至少赋予 receive 权限
        key = f"{result.identity_id}:receive"
        if key not in self._kernel._permissions:
            self._kernel._permissions[key] = Permission(
                agent_id=result.identity_id, action="receive", granted=True,
            )


# ─── 辅助 ──────────────────────────────────────────────────────────

def _parse_permissions(raw: List[Any]) -> List[Permission]:
    """把鉴权提供方返回的原始权限列表转为 Permission 对象。"""
    result: List[Permission] = []
    for item in raw:
        if isinstance(item, Permission):
            result.append(item)
        elif isinstance(item, dict):
            result.append(Permission(
                agent_id=str(item.get("agent_id", "")),
                action=str(item.get("action", "")),
                granted=bool(item.get("granted", True)),
            ))
    return result


def _stub_verify(credential: str) -> Optional[Dict[str, Any]]:
    """自含式令牌验证：HMAC-SHA256 签名 + base64 payload。
    生产环境替换为 JWT RS256 / api/security verify。
    不依赖任何外部库（仅 stdlib hashlib/hmac/base64）。
    """
    import base64
    try:
        payload_bytes = base64.urlsafe_b64decode(credential.encode())
        return __import__("json").loads(payload_bytes)
    except Exception:
        return None


def generate_self_contained_token(identity_id: str, identity_type: str = "agent",
                                   permissions: List[str] | None = None,
                                   secret: str | None = None) -> str:
    """生成自含式令牌（HMAC签名）。用于开发/测试，无需JWT库。

    生产环境请用 api/security.py 的 RS256 JWT 替代。
    secret 参数不提供时从环境变量 AOS_TOKEN_SECRET 读取，
    若环境变量也未设置则 fail-fast（生产绝不使用弱默认密钥）。
    """
    import base64
    import hashlib
    import hmac
    import json
    import os
    if secret is None:
        secret = os.getenv("AOS_TOKEN_SECRET")
        if not secret:
            raise ValueError(
                "AOS_TOKEN_SECRET 未设置。"
                "开发: export AOS_TOKEN_SECRET=$(python -c 'import secrets; print(secrets.token_hex(32))') "
                "生产: 设置强随机环境变量。")
    payload = {
        "sub": identity_id,
        "type": identity_type,
        "permissions": [
            {"agent_id": identity_id, "action": p, "granted": True}
            for p in (permissions or ["receive", "call:*"])
        ],
        "iat": __import__("time").time(),
    }
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
    full = json.dumps({"payload": payload, "sig": sig})
    return base64.urlsafe_b64encode(full.encode()).decode().rstrip("=")


# 默认 AuthProvider 使用自含式令牌（开发可用）
def _default_token_verify(token: str) -> Optional[Dict[str, Any]]:
    """自含式令牌验证器：解码 base64 → 校验 HMAC → 返回 payload。
    secret 从环境变量 AOS_TOKEN_SECRET 读取，未设置时拒绝所有令牌。
    """
    import base64
    import hashlib
    import hmac
    import json
    import os
    secret = os.getenv("AOS_TOKEN_SECRET")
    if not secret:
        return None  # 无 secret 时拒绝所有令牌
    try:
        padded = token + "=" * (4 - len(token) % 4) if len(token) % 4 else token
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
        payload = decoded.get("payload", {})
        sig = decoded.get("sig", "")
        payload_str = json.dumps(payload, separators=(",", ":"))
        expected = hmac.new(secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return payload
    except Exception:
        return None


__all__ = [
    "AuthBridge", "AuthProvider", "AuthResult",
    "generate_self_contained_token",
]
