"""
RateLimitMiddleware 实证测试（②级，offline，无网络/无 LLM）。

目的：用确定性单测证明「限流粒度单一」(#3 审查指控) 在代码层面不成立——
当前中间件已实现 **IP 维度 + API Key(租户) 维度** 双粒度限流，且两维度互相隔离。

AOS 的租户由 API Key 解析（api/danchuang_api.py:71 _get_tenant_from_key），
故 API Key 级限流本质上即租户级限流。测试据此实证多维度隔离，非全局单一计数。

注意：import api.security 会触发 DeerFlow 口令模块副作用，测试前先设固定口令避免写盘。
"""
import os

os.environ.setdefault("AOS_DEERFLOW_ADMIN_PASSWORD", "test-fixed-password-for-rate-limit-tests")

import asyncio
from starlette.requests import Request
from starlette.responses import Response

from api.security import RateLimitMiddleware


def _scope(client_ip, api_key=None):
    headers = []
    if api_key:
        headers.append((b"x-api-key", api_key.encode()))
    return {"type": "http", "client": (client_ip, 1234), "headers": headers}


async def _nxt(request):
    return Response("ok", status_code=200)


def _fire(mw, client_ip, api_key=None):
    req = Request(_scope(client_ip, api_key))
    return asyncio.run(mw.dispatch(req, _nxt))


class TestIpDimension:
    def test_ip_dimension_isolated_not_global(self):
        # 同一 IP 打满 limit(3) → 第 4 次 429；换 IP 仍 200，证明非全局单一计数。
        mw = RateLimitMiddleware(_nxt, max_requests=3, time_window_seconds=60)
        ip = "1.1.1.1"
        for _ in range(3):
            assert _fire(mw, ip).status_code == 200
        assert _fire(mw, ip).status_code == 429
        # 不同 IP 不受影响（维度隔离）
        assert _fire(mw, "2.2.2.2").status_code == 200

    def test_ip_budget_independent_per_ip(self):
        mw = RateLimitMiddleware(_nxt, max_requests=2, time_window_seconds=60)
        assert _fire(mw, "3.3.3.3").status_code == 200
        assert _fire(mw, "3.3.3.3").status_code == 200
        assert _fire(mw, "3.3.3.3").status_code == 429
        # 另一个 IP 仍有自己的 2 次预算
        assert _fire(mw, "4.4.4.4").status_code == 200
        assert _fire(mw, "4.4.4.4").status_code == 200
        assert _fire(mw, "4.4.4.4").status_code == 429


class TestApiKeyDimension:
    def test_apikey_dimension_separate_from_ip(self):
        # IP 维度打满后，带有效 API Key 的同 IP 走 api_key 维度（3x 配额），不受 IP 满影响。
        mw = RateLimitMiddleware(_nxt, max_requests=3, time_window_seconds=60)
        ip = "5.5.5.5"
        for _ in range(3):
            assert _fire(mw, ip).status_code == 200
        assert _fire(mw, ip).status_code == 429  # IP 维度满
        # 带 API Key：走独立维度，仍 200
        assert _fire(mw, ip, api_key="k" * 20).status_code == 200

    def test_apikey_enjoys_triple_quota(self):
        # 认证用户配额 = max_requests * 3 = 9；IP 匿名仅 3。
        mw = RateLimitMiddleware(_nxt, max_requests=3, time_window_seconds=60)
        key = "a" * 20
        for i in range(9):
            assert _fire(mw, "6.6.6.6", api_key=key).status_code == 200, f"第{i+1}次应放行"
        # 第 10 次超 9 配额 → 429
        assert _fire(mw, "6.6.6.6", api_key=key).status_code == 429

    def test_apikey_truncated_to_32_shared_bucket(self):
        # 隐私保护：key 截断前 32 位计桶。两 key 前 32 位相同 → 同一桶。
        mw = RateLimitMiddleware(_nxt, max_requests=3, time_window_seconds=60)
        k1 = "a" * 40
        k2 = "a" * 32 + "b" * 8  # 前 32 位与 k1 相同
        for _ in range(9):
            assert _fire(mw, "7.7.7.7", api_key=k1).status_code == 200
        assert _fire(mw, "7.7.7.7", api_key=k1).status_code == 429
        # k2 与 k1 同桶 → 也 429
        assert _fire(mw, "7.7.7.7", api_key=k2).status_code == 429


class TestResponseHeaders:
    def test_429_headers_present(self):
        mw = RateLimitMiddleware(_nxt, max_requests=2, time_window_seconds=60)
        ip = "8.8.8.8"
        assert _fire(mw, ip).status_code == 200
        assert _fire(mw, ip).status_code == 200
        r = _fire(mw, ip)
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "60"
        assert r.headers["X-RateLimit-Limit"] == "2"
        assert r.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in r.headers

    def test_200_sets_limit_and_remaining_headers(self):
        mw = RateLimitMiddleware(_nxt, max_requests=5, time_window_seconds=60)
        r = _fire(mw, "9.9.9.9")
        assert r.status_code == 200
        assert r.headers["X-RateLimit-Limit"] == "5"
        assert r.headers["X-RateLimit-Remaining"] == "4"
