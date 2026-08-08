"""多租户 API Key 网关守门测试（2026-08-08 实跑发现死锁后新增）。

背景（真实故障，非假设）：
    单创OS 给租户签发自己的 key（sk-xxx，存 tenants.db），而 `api/security.py`
    的全局中间件校验的是平台级 `config.API_KEY`，两者共用同一个 `X-API-Key` 头。
    中间件的「本地回环豁免」是 fail-closed（一旦显式带凭据就必须校验通过），
    于是租户两头堵死 —— 真机 uvicorn 实测：

        GET /api/danchuang/tenant  不带凭据  → 401 {"message":"缺少 API Key"}     (子系统拒)
        GET /api/danchuang/tenant  带租户key → 401 {"detail":"Invalid ... API Key"} (中间件拒)

    结论：租户永远拿不到自己的数据，多租户 SaaS 模式根本跑不通 = 上线致命阻断。

修法：`security.register_api_key_validator()` 注册表。子系统把「这个 key 是不是我签发的」
注册进来，中间件平台 key 校验失败后逐个尝试。security.py 不 import 任何子系统（零耦合）。

本测试锁死四件事：
    1. 注册表机制本身可用（注册 → 生效 → 清空 → 失效）
    2. 校验器抛异常不能打断鉴权链（只能等价于「不认识这个 key」）
    3. 未注册时行为与修复前完全一致（向后兼容，不放行任何未知 key）
    4. danchuang 模块确实完成了注册（防止有人重构时把注册代码删掉）
"""
from __future__ import annotations

import pytest

from api import security


@pytest.fixture(autouse=True)
def _isolate_validators():
    """每个用例前后都清空注册表，避免相互污染。"""
    saved = list(security._ADDITIONAL_KEY_VALIDATORS)
    security.clear_api_key_validators()
    yield
    security.clear_api_key_validators()
    for fn in saved:
        security.register_api_key_validator(fn)


def _middleware():
    """构造中间件实例，只为拿到 _check_api_key，不启动 ASGI 栈。"""
    return security.APISecurityMiddleware(app=lambda scope, receive, send: None)


# ──────────────────────────────────────────────────────────────
# 1. 注册表机制
# ──────────────────────────────────────────────────────────────

def test_registered_validator_lets_subsystem_key_pass():
    """回归：租户 key 必须能穿过全局中间件（修复前恒为 False → 401 死锁）。"""
    mw = _middleware()
    assert mw._check_api_key("sk-tenant-abc") is False, "注册前不应放行"

    security.register_api_key_validator(lambda k: k == "sk-tenant-abc")
    assert mw._check_api_key("sk-tenant-abc") is True, "注册后应放行本子系统 key"


def test_unknown_key_still_rejected_after_registration():
    """反向验证：开了口子不等于放行一切，未知 key 必须仍被拒（防越权）。"""
    security.register_api_key_validator(lambda k: k == "sk-tenant-abc")
    mw = _middleware()
    for bad in ["sk-fake-nonexistent", "random-garbage", "", "sk-"]:
        assert mw._check_api_key(bad) is False, f"伪造 key 被放行，存在越权风险: {bad!r}"


def test_registration_is_idempotent():
    """同一函数重复注册只保留一份，避免热重载时无限堆积。"""
    def v(_k: str) -> bool:
        return False

    security.register_api_key_validator(v)
    security.register_api_key_validator(v)
    security.register_api_key_validator(v)
    assert len(security._ADDITIONAL_KEY_VALIDATORS) == 1


def test_no_validator_registered_keeps_original_behavior():
    """向后兼容：没有任何子系统注册时，行为与修复前完全一致。"""
    mw = _middleware()
    assert mw._check_api_key("anything") is False
    assert mw._check_api_key("") is False


# ──────────────────────────────────────────────────────────────
# 2. 健壮性：校验器崩溃不能拖垮鉴权链
# ──────────────────────────────────────────────────────────────

def test_crashing_validator_does_not_break_auth_chain():
    """一个子系统的校验器炸了，不能让整个 API 的鉴权跟着炸。"""
    def boom(_k: str) -> bool:
        raise RuntimeError("模拟子系统数据库连不上")

    security.register_api_key_validator(boom)
    security.register_api_key_validator(lambda k: k == "sk-good")

    mw = _middleware()
    assert mw._check_api_key("sk-good") is True, "前一个校验器崩溃不应阻断后续校验器"
    assert mw._check_api_key("sk-bad") is False, "全部校验器都不认时必须拒绝"


# ──────────────────────────────────────────────────────────────
# 3. danchuang 必须真的完成注册（防重构时被删）
# ──────────────────────────────────────────────────────────────

def test_danchuang_registers_its_tenant_key_validator():
    """挂载单创OS 路由后，租户 key 校验器必须出现在注册表里。"""
    from fastapi import FastAPI

    from api import danchuang_api

    security.clear_api_key_validators()
    danchuang_api.register_routes(FastAPI())

    assert security._ADDITIONAL_KEY_VALIDATORS, (
        "单创OS 挂载后没有注册租户 Key 校验器 —— 多租户模式会退回 401 死锁"
    )
