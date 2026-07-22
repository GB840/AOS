"""统一 opt-in 外部能力扩展注册（单创OS 可插拔架构）。

用户要求：所有能扩展的都留接口，不单单是 WorkRally。
本模块提供统一机制：任何外部服务（WorkRally、未来任何 SaaS/开源服务）
都走此注册 —— env 门控、不可达静默跳过、可选本地红线。

范式来源：复用 fabric_hub.register_mcp_server / register_weknora_mcp
（env-gated、opt-in、失败返回 None 静默跳过）。这里把它标准化为一个
轻量注册表，避免每接一个外部服务就复制一套样板。
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional


_EXTENSIONS: Dict[str, Dict[str, Any]] = {}


def register_extension(
    name: str,
    factory: Callable[[], Any],
    *,
    env_gate: Optional[str] = None,
    local_only: bool = False,
    description: str = "",
) -> None:
    """注册一个 opt-in 扩展。

    name:       扩展标识（如 "workrally"）
    factory:    无参工厂，返回实例；不可达/未配置应返回 None 或抛异常
    env_gate:   需该 env 为真才启用（如 "WORKRALLY_TOKEN"）
    local_only: True 时禁止外部网络，只接 localhost（安全红线）
    description:人读说明
    """
    _EXTENSIONS[name] = {
        "factory": factory,
        "env_gate": env_gate,
        "local_only": local_only,
        "description": description,
    }


def is_enabled(name: str) -> bool:
    meta = _EXTENSIONS.get(name)
    if not meta:
        return False
    if meta["env_gate"] and not os.environ.get(meta["env_gate"]):
        return False
    return True


def get_extension(name: str) -> Any:
    """启用且工厂成功才返回实例；否则 None（静默跳过）。

    调用方据此决定：返回 None 时不阻断主链路，仅缺失该可选能力。
    """
    meta = _EXTENSIONS.get(name)
    if not meta or not is_enabled(name):
        return None
    try:
        return meta["factory"]()
    except Exception:
        return None


def list_extensions() -> Dict[str, Dict[str, Any]]:
    return {
        k: {
            "enabled": is_enabled(k),
            "description": v["description"],
            "local_only": v["local_only"],
        }
        for k, v in _EXTENSIONS.items()
    }


# ── WorkRally 接口位（opt-in，暂不实现真实调用）──
# 腾讯视频「精品漫剧工业级 AI 生产平台」（闭源商业，2026-04-16 发布）。
# 用户暂无账号 -> 仅留接口，不引入任何腾讯依赖。
# 启用条件：配置 WORKRALLY_TOKEN（用户显式同意付费授权）。
# 未来真实实现：WorkRallyAdapter 调 workrally CLI / Open API，
#   映射为 content.workrally capability，供内容营销岗可选增强。
# 设计红线：绝不默认启用；绝不作为核心路径；纯可选云端增强。
def _workrally_factory() -> Any:
    # TODO: 实现 WorkRallyAdapter（auth login + 调用漫剧生产流水线）
    # 当前返回 None -> get_extension("workrally") 静默跳过
    return None


register_extension(
    "workrally",
    _workrally_factory,
    env_gate="WORKRALLY_TOKEN",
    local_only=False,
    description="腾讯视频 WorkRally 漫剧生产平台（opt-in，需授权账号，仅可选增强）",
)
