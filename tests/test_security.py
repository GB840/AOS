"""安全中间件与认证相关单元测试 (对应整改 #108/#109/#113/#114/#115)。

覆盖:
- APISecurityMiddleware: 公开端点/受保护端点/文档生产禁用 (G2/G3/G4)。
- JWT RS256 签发/校验 (替代 HS256, G1) + 恒定时间比较 (G5)。
- 审计日志脱敏与错误详情脱敏 (G7)。
- 受限 AST 表达式求值器 (替代 eval, #112)。
- HTTPSRedirectMiddleware 尊重反向代理 X-Forwarded-Proto (#113)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import jwt as _jwt
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from utils.config import config as APP_CONFIG
from api.security import (
    APISecurityMiddleware,
    HTTPSRedirectMiddleware,
    authenticate_user,
    create_access_token,
    decode_access_token,
    generate_api_key,
)
from utils.keystore import generate_strong_password, load_jwt_keys
from utils.sanitize import mask_secret, mask_dict, safe_error_detail
from skills.safe_eval import safe_eval_expr


# ---------- 安全中间件 (G2/G3/G4) ----------

@pytest.fixture
def sec_client(monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "APP_ENV", "production")
    monkeypatch.setattr(APP_CONFIG, "API_KEY", "test-key-12345")
    app = FastAPI()
    app.add_middleware(APISecurityMiddleware)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/protected")
    def protected():
        return {"secret": "x"}

    @app.get("/docs")
    def docs():
        return {"docs": True}

    return TestClient(app)


def test_public_health_no_auth(sec_client):
    assert sec_client.get("/health").status_code == 200


def test_protected_requires_key(sec_client):
    # 无 key -> 401
    assert sec_client.get("/api/protected").status_code == 401
    # 正确 key -> 200
    r = sec_client.get("/api/protected", headers={"X-API-Key": "test-key-12345"})
    assert r.status_code == 200
    # 错误 key -> 401
    assert sec_client.get("/api/protected", headers={"X-API-Key": "wrong"}).status_code == 401


def test_docs_blocked_in_prod(sec_client):
    assert sec_client.get("/docs").status_code == 401


def test_docs_open_in_dev(monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "APP_ENV", "development")
    monkeypatch.setattr(APP_CONFIG, "API_KEY", "test-key-12345")
    app = FastAPI()
    app.add_middleware(APISecurityMiddleware)

    @app.get("/docs")
    def docs():
        return {"docs": True}

    assert TestClient(app).get("/docs").status_code == 200


# ---------- HTTPS 强制 (#113) ----------

def test_https_redirect_prod_http_redirects_https(monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "APP_ENV", "production")
    app = FastAPI()
    app.add_middleware(HTTPSRedirectMiddleware)

    @app.get("/")
    def root():
        return {"ok": True}

    # 明文 http -> 301 跳 https (TestClient 默认跟随重定向, 这里关闭以断言状态码)
    r = TestClient(app, follow_redirects=False).get("/")
    assert r.status_code == 301
    assert r.headers["location"].startswith("https://")
    # 经 https base_url -> 200 (X-Forwarded-Proto 路径同源)
    r2 = TestClient(app, base_url="https://testserver").get("/")
    assert r2.status_code == 200
    # 反向代理透传 X-Forwarded-Proto: https -> 不再重定向
    r3 = TestClient(app).get("/", headers={"X-Forwarded-Proto": "https"})
    assert r3.status_code == 200


# ---------- JWT RS256 (G1) ----------

def test_jwt_api_roundtrip(monkeypatch, tmp_path):
    priv, pub = load_jwt_keys(base_dir=tmp_path, app_env="development", force_generate=True)
    import api.security as sec
    monkeypatch.setattr(sec, "_get_jwt_keys", lambda: (priv, pub))
    tok = create_access_token("alice")
    assert decode_access_token(tok) == "alice"
    # 篡改令牌 -> None
    assert decode_access_token(tok + "x") is None


# ---------- 恒定时间比较 (G5) ----------

def test_authenticate_user_constant_time(monkeypatch):
    monkeypatch.setattr(APP_CONFIG, "ADMIN_USERNAME", "admin")
    monkeypatch.setattr(APP_CONFIG, "ADMIN_PASSWORD", "s3cret!")
    assert authenticate_user("admin", "s3cret!") is True
    assert authenticate_user("admin", "wrong") is False
    assert authenticate_user("root", "s3cret!") is False


def test_generate_api_key_entropy():
    k1, k2 = generate_api_key(), generate_api_key()
    assert len(k1) >= 32
    assert k1 != k2


# ---------- 密钥治理 (keystore) ----------

def test_strong_password_and_rsa(tmp_path):
    pw = generate_strong_password(24)
    assert len(pw) >= 24
    assert pw != generate_strong_password(24)  # 每次不同
    priv, pub = load_jwt_keys(base_dir=tmp_path, app_env="development", force_generate=True)
    assert priv.startswith("-----BEGIN")
    assert "PUBLIC KEY" in pub
    tok = _jwt.encode({"sub": "bob"}, priv, algorithm="RS256")
    assert _jwt.decode(tok, pub, algorithms=["RS256"])["sub"] == "bob"


# ---------- 日志/错误脱敏 (G7, #114) ----------

def test_sanitize_helpers():
    assert safe_error_detail(Exception("ZeroDivisionError"), "production") == "Internal server error"
    assert "ZeroDivisionError" in safe_error_detail(Exception("ZeroDivisionError"), "development")
    m = mask_secret("TK-abcdefghij1234")
    assert m.startswith("TK-a") and len(m) == len("TK-abcdefghij1234")
    d = mask_dict({"api_key": "TK-secret", "user": "alice", "nested": {"password": "hunter2"}})
    assert d["api_key"] != "TK-secret" and d["user"] == "alice"
    assert d["nested"]["password"] != "hunter2"


# ---------- 受限 AST 求值器 (#112) ----------

def test_safe_eval_allows_valid_blocks_injection(tmp_path):
    VR = lambda rule, result: safe_eval_expr(rule, {"result": result})
    assert VR('result["success"] == True', {"success": True}) is True
    assert VR('len(result["items"]) > 2', {"items": [1, 2, 3, 4]}) is True
    assert VR('result["x"] is None', {"x": None}) is True
    # 注入必须被拒且绝不执行
    import os
    probe = str(tmp_path / "__eval_probe__.txt")
    if os.path.exists(probe):
        os.remove(probe)
    inj = f'result["x"] == "y"; __import__("os").system("echo pwned > {probe}")'
    assert VR(inj, {"x": "y"}) is False
    assert os.path.exists(probe) is False
    assert VR('result.__class__', {"x": 1}) is False
    assert VR('__import__("os")', {}) is False
