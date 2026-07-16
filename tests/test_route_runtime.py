"""路由预测运行时装配测试（轻量，不加载重型适配器）。

只验证 build_route_runtime() 的接线契约：默认启用 learned 且带 predictor；
AOS_ROUTE_STRATEGY=preference 时 predictor=None（回落静态，零影响）。
"""
from __future__ import annotations

import os

from core.fabric.route_runtime import build_route_runtime


def test_default_strategy_is_learned_with_predictor(monkeypatch):
    monkeypatch.delenv("AOS_ROUTE_STRATEGY", raising=False)
    rt = build_route_runtime()
    assert rt["strategy"] == "learned"
    assert rt["predictor"] is not None
    assert rt["outcome_store"] is not None
    assert rt["predictor_path"]
    # 无磁盘模型时 predictor 是未训练的全新实例
    assert rt["predictor"].trained is False


def test_preference_strategy_disables_predictor(monkeypatch):
    monkeypatch.setenv("AOS_ROUTE_STRATEGY", "preference")
    rt = build_route_runtime()
    assert rt["strategy"] == "preference"
    assert rt["predictor"] is None  # learned 关 → 不建 predictor，回落静态
