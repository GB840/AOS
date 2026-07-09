"""日志/审计脱敏工具。

集中处理"不要把密钥/令牌/口令回显到日志或客户端"的需求:
- mask_secret(): 仅保留前 N 位, 其余打码, 用于审计日志中记录密钥前缀 (可溯源但不泄露)。
- mask_dict(): 递归脱敏 dict 中疑似密钥字段, 防止把含凭据的结构体直接 logger.info。
"""
import re
from typing import Any, Dict

# 命中这些字段名的 value 视为敏感, 需脱敏。
_SECRET_FIELD_RE = re.compile(
    r"(?i)(api[_-]?key|apikey|access[_-]?key|secret|token|passwd|password|"
    r"authorization|bearer|private[_-]?key|client[_-]?secret|credential)"
)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return value[:visible] + "*" * (len(value) - visible)


def mask_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = mask_dict(v)
        elif isinstance(v, str) and _SECRET_FIELD_RE.search(str(k)):
            out[k] = mask_secret(v)
        else:
            out[k] = v
    return out


def safe_error_detail(e: Exception, app_env: str = "development") -> str:
    """G7: 生产环境返回通用错误文案, 不泄露内部异常细节; 非生产返回原文。

    调用方应在生产分支同时把真实异常写入服务端日志 (logger.error(..., exc_info=True))。
    """
    if app_env == "production":
        return "Internal server error"
    return str(e)
