"""路由预测运行时装配：把「白盒进化」接线成可注入 FabricRegistry 的 kwargs。

默认启用 learned 策略（AOS_ROUTE_STRATEGY 缺省 = learned）；可用
AOS_ROUTE_STRATEGY=preference 一键退化为静态偏好表（predictor=None，零影响）。
模型与落盘数据位于 <repo>/src/_traces/，已在 .gitignore。
"""
from __future__ import annotations

import os

from .route_predictor import RoutePredictor
from .route_outcome_store import RouteOutcomeStore

# src/_traces/：与 RouteOutcomeStore 默认目录一致（route_outcome_store.py 位于
# src/core/fabric，向上数三级得到 src）。本模块同处 src/core/fabric，向上三级即 src。
_TRACES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "_traces",
)
_OUTCOME_PATH = os.path.join(_TRACES_DIR, "route_outcomes.jsonl")
_PREDICTOR_PATH = os.path.join(_TRACES_DIR, "route_predictor.json")


def build_route_runtime() -> dict:
    """构造传给 FabricRegistry 的运行时 kwargs。

    返回含 strategy / predictor / outcome_store / predictor_path。
    仅当 strategy=="learned" 才构建 predictor；若磁盘已有训练好的模型则加载，
    否则新建未训练实例（由真实流量触发 maybe_retrain 后训练并持久化）。
    """
    strategy = os.environ.get("AOS_ROUTE_STRATEGY", "learned")
    predictor = None
    if strategy == "learned":
        try:
            if os.path.exists(_PREDICTOR_PATH):
                predictor = RoutePredictor.load(_PREDICTOR_PATH)
            else:
                predictor = RoutePredictor()
        except Exception:  # noqa: BLE001 - 模型损坏则退回全新，不阻断枢纽构建
            predictor = RoutePredictor()
    return {
        "strategy": strategy,
        "predictor": predictor,
        "outcome_store": RouteOutcomeStore(path=_OUTCOME_PATH),
        "predictor_path": _PREDICTOR_PATH,
    }
