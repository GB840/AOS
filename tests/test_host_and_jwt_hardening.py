"""Host 头白名单 + JWT claim 校验加固回归测试。

背景（审查报告 #1 / #2，均核实为真）：
- #1 应用没有挂 ``TrustedHostMiddleware``：任意 Host 头都被接受，可用于
  缓存投毒、密码重置链接劫持、内网跳板探测。
- #2 ``decode_access_token`` 只校验签名与 ``exp``，不校验 ``iss`` / ``aud`` / ``nbf``：
  任何持同一把公钥的兄弟服务签发的令牌都能横向复用到本 API。

外加本轮发现的第三个真问题（既有失败测试暴露）：
- 本地回环免鉴权分支排在 JWT 校验之前且无条件放行，导致"本机 + 无效 Bearer"
  被静默放行成 200。已改为 fail-closed：不带凭据才免鉴权，带了就必须有效。

诚实分级：② 级（代码 + 单测实证）。未做真实网络部署下的 ③ 级端到端验证。
"""
from __future__ import annotations

import os
import sys
import time

import pytest
from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import src.api.security as security_mod  # noqa: E402
from utils.config import config  # noqa: E402


# ─── #1 Host 头白名单 ───────────────────────────────────────────

def _host_app():
    async def ok(_request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/", ok)])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["aos.local", "127.0.0.1"])
    return app


def test_allowed_host_passes():
    with TestClient(_host_app(), base_url="http://aos.local") as c:
        assert c.get("/").status_code == 200


def test_forged_host_rejected():
    with TestClient(_host_app(), base_url="http://evil.example.com") as c:
        assert c.get("/").status_code == 400, "伪造 Host 未被拒绝"


def test_real_app_has_trusted_host_as_outermost_middleware():
    """真实 app 必须挂上 Host 白名单，且排在最外层（最先执行）。"""
    main = pytest.importorskip("src.api.main", reason="API 依赖未装齐")
    names = [mw.cls.__name__ for mw in main.app.user_middleware]
    assert "TrustedHostMiddleware" in names, f"未挂 Host 白名单: {names}"
    assert names[0] == "TrustedHostMiddleware", (
        f"Host 校验必须是最外层第一道门，当前顺序: {names}"
    )


def test_config_exposes_allowed_hosts():
    assert hasattr(config, "ALLOWED_HOSTS")
    hosts = [h.strip() for h in config.ALLOWED_HOSTS.split(",") if h.strip()]
    assert hosts, "ALLOWED_HOSTS 不应为空"


# ─── #2 JWT claim 校验 ─────────────────────────────────────────

def _forge(payload: dict) -> str:
    """用真实私钥签一个 payload 可控的 token（签名合法，claim 不合法）。"""
    jwt = security_mod._import_jwt()
    private_pem, _pub = security_mod._get_jwt_keys()
    return jwt.encode(payload, private_pem, algorithm=config.AUTH_JWT_ALGORITHM)


def _base_claims(**over) -> dict:
    now = int(time.time())
    claims = {
        "sub": "tester",
        "iat": now,
        "nbf": now,
        "exp": now + 600,
        "iss": config.AUTH_JWT_ISSUER,
        "aud": config.AUTH_JWT_AUDIENCE,
    }
    claims.update(over)
    return claims


def test_issued_token_carries_all_claims():
    jwt = security_mod._import_jwt()
    token = security_mod.create_access_token("tester")
    _priv, pub = security_mod._get_jwt_keys()
    payload = jwt.decode(
        token, pub, algorithms=[config.AUTH_JWT_ALGORITHM],
        issuer=config.AUTH_JWT_ISSUER, audience=config.AUTH_JWT_AUDIENCE,
    )
    for claim in ("sub", "iat", "nbf", "exp", "iss", "aud"):
        assert claim in payload, f"签发的令牌缺少 {claim}"


def test_roundtrip_valid():
    token = security_mod.create_access_token("tester")
    sub, st = security_mod.decode_access_token(token)
    assert (sub, st) == ("tester", "valid")


def test_wrong_issuer_rejected():
    """兄弟服务用同一把私钥签的令牌不能进本 API。"""
    sub, st = security_mod.decode_access_token(_forge(_base_claims(iss="other-service")))
    assert sub is None and st == "invalid"


def test_wrong_audience_rejected():
    sub, st = security_mod.decode_access_token(_forge(_base_claims(aud="other-api")))
    assert sub is None and st == "invalid"


def test_future_nbf_rejected():
    """未到生效时间的令牌不可用（leeway 之外）。"""
    future = int(time.time()) + 3600
    sub, st = security_mod.decode_access_token(
        _forge(_base_claims(nbf=future, iat=future))
    )
    assert sub is None and st == "invalid"


def test_legacy_token_without_iss_aud_rejected():
    """只有 sub/iat/exp 的旧格式令牌（本次加固前的签发结果）必须被拒。"""
    now = int(time.time())
    legacy = _forge({"sub": "tester", "iat": now, "exp": now + 600})
    sub, st = security_mod.decode_access_token(legacy)
    assert sub is None and st == "invalid"


def test_expired_token_still_reported_as_expired():
    """过期仍要能与'无效'区分开，前端才能触发静默续期而不是弹登录。"""
    now = int(time.time())
    expired = _forge(_base_claims(iat=now - 7200, nbf=now - 7200, exp=now - 3600))
    sub, st = security_mod.decode_access_token(expired)
    assert sub is None and st == "expired"


def test_garbage_token_rejected():
    sub, st = security_mod.decode_access_token("not-a-jwt")
    assert sub is None and st in ("invalid", "error")


# ─── 本地回环 fail-closed ──────────────────────────────────────

def test_localhost_without_credentials_still_exempt():
    """母纲"本地优先、打开即用"：本机不带凭据仍免鉴权。"""
    mw = security_mod.APISecurityMiddleware(app=lambda *a, **k: None)
    scope = {
        "type": "http", "method": "GET", "path": "/api/x",
        "headers": [], "query_string": b"", "client": ("127.0.0.1", 1234),
    }
    from starlette.requests import Request
    assert mw._has_explicit_credentials(Request(scope)) is False


def test_localhost_with_credentials_is_checked():
    """本机带了凭据 → 视为走鉴权路径，不再豁免。"""
    mw = security_mod.APISecurityMiddleware(app=lambda *a, **k: None)
    from starlette.requests import Request
    for headers in ([(b"authorization", b"Bearer whatever")],
                    [(security_mod.API_KEY_NAME.lower().encode(), b"some-key")]):
        scope = {
            "type": "http", "method": "GET", "path": "/api/x",
            "headers": headers, "query_string": b"", "client": ("127.0.0.1", 1234),
        }
        assert mw._has_explicit_credentials(Request(scope)) is True


def test_blank_authorization_header_is_not_credentials():
    """空的 Authorization 头不算携带凭据，避免误伤本机客户端。"""
    mw = security_mod.APISecurityMiddleware(app=lambda *a, **k: None)
    from starlette.requests import Request
    scope = {
        "type": "http", "method": "GET", "path": "/api/x",
        "headers": [(b"authorization", b"   ")], "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }
    assert mw._has_explicit_credentials(Request(scope)) is False
