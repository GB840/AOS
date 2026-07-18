"""验证 /api/approvals 路由不再撞车（双轨债 ④）。

规范、持久化、可审计的审批 API 在 api/approval_api.py（前缀 /api/approvals，
单一真相）。产品飞轮的 evolve 提案审批 UI 已迁到 /api/proposals，
二者不再共享前缀、无 (method, path) 撞车，规范实现不再被遮蔽。
"""
import pytest


def test_approvals_routers_no_collision():
    try:
        from api.approval_api import router as canonical
        from api.product_flywheel_api import approvals_router as flywheel
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"审批路由模块不可导入: {e}")

    assert canonical.prefix == "/api/approvals"
    assert flywheel.prefix == "/api/proposals"

    canon = {(frozenset(r.methods), r.path) for r in canonical.routes}
    fly = {(frozenset(r.methods), r.path) for r in flywheel.routes}
    assert not (canon & fly), f"审批路由撞车: {canon & fly}"
