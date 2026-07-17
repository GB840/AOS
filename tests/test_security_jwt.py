"""测试 APISecurityMiddleware 对 JWT 过期/无效/有效的区分（直接测 dispatch）。

不走完整 TestClient(app) 链路（那条链路在 pytest 里 monkeypatch 类方法易失准），
而是直接构造中间件实例、注入 mock 的 decode_access_token、用最小 Request 调 dispatch，
验证真实中间件代码对三种 token 状态的 HTTP 响应区分。
"""
import asyncio
import json

from starlette.requests import Request
from starlette.responses import Response

import src.api.security as security_mod


def _make_request(path: str = "/api/sandbox/exec", auth: str = None):
    headers = {}
    if auth:
        headers["Authorization"] = auth
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


def _make_middleware():
    # app 参数仅占位；dispatch 不依赖真实下游，call_next 由测试提供。
    mw = security_mod.APISecurityMiddleware(app=lambda *a, **k: None)
    # 强制开启统一鉴权（测试环境可能未配 API Key 导致 _auth_enabled=False 而跳过）。
    mw._auth_enabled = True
    return mw


def test_jwt_expired_token(monkeypatch):
    """过期 Token 返回 401 + detail='token expired'。"""
    monkeypatch.setattr(security_mod, "decode_access_token", lambda token: (None, "expired"))
    mw = _make_middleware()
    passed = {}

    async def call_next(request):
        passed["hit"] = True
        return Response("ok")

    resp = asyncio.run(mw.dispatch(_make_request(auth="Bearer expired-token"), call_next))
    assert resp.status_code == 401
    body = json.loads(resp.body)
    assert body["detail"] == "token expired"
    assert not passed.get("hit")   # 过期 token 不应放行到下游


def test_jwt_invalid_token(monkeypatch):
    """无效 Token 返回 401 + detail='invalid'。"""
    monkeypatch.setattr(security_mod, "decode_access_token", lambda token: (None, "invalid"))
    mw = _make_middleware()
    passed = {}

    async def call_next(request):
        passed["hit"] = True
        return Response("ok")

    resp = asyncio.run(mw.dispatch(_make_request(auth="Bearer invalid-token"), call_next))
    assert resp.status_code == 401
    body = json.loads(resp.body)
    assert body["detail"] == "invalid"
    assert not passed.get("hit")


def test_jwt_valid_token(monkeypatch):
    """有效 Token 放行到下游（call_next 被调用）。"""
    monkeypatch.setattr(security_mod, "decode_access_token", lambda token: ("test_user", "valid"))
    mw = _make_middleware()
    passed = {}

    async def call_next(request):
        passed["hit"] = True
        return Response("ok")

    resp = asyncio.run(mw.dispatch(_make_request(auth="Bearer valid-token"), call_next))
    assert passed.get("hit") is True
    assert resp.status_code == 200
