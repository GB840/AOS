"""MEA Auditor 角色：只读独立验证环境事实。

对应 LongHorizon-Harness 的 Auditor —— 仅通过检查**文件 / 日志**等环境事实确认任务是否完成；
只有审计通过的结果才能写入持久状态（run_state_store 的 AuditorGate / verified_milestones 层）。

用法：
    from kernel.auditor import build_default_auditor
    from kernel.run_state_store import set_auditor
    set_auditor(build_default_auditor())

契约（给 run_state_store 的 ``_AUDITOR`` 用）：
    auditor(state: dict, run_id: str) -> bool
    - ``state`` 含 ``"verify"`` 字段（验证规格 dict）时，逐项独立核查环境事实；
      任一核查失败 → 返回 False（Gate 拒绝写入 / propose_milestone 抛错）。
    - ``state`` 不含 ``verify`` → 默认放行（向后兼容：既有 checkpoint 不带验证规格）。
    - 核查过程**只读**，绝不修改任何状态或环境。
"""
from __future__ import annotations

import logging
import os
import re

_LOG = logging.getLogger("auditor")


def _check_file(path) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _check_files(paths) -> bool:
    if not isinstance(paths, (list, tuple)):
        paths = [paths]
    return all(_check_file(p) for p in paths)


def _check_contains(spec) -> bool:
    """spec: {"path": str, "pattern": str} —— 文件存在且匹配正则。"""
    if not isinstance(spec, dict):
        return False
    path = spec.get("path")
    pattern = spec.get("pattern")
    if not path or not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return False
    return bool(re.search(pattern, text)) if pattern else True


DEFAULT_CHECKS = {
    "file": lambda v: _check_file(v),
    "files": _check_files,
    "contains": _check_contains,
}


class EnvironmentAuditor:
    """只读环境事实审计器。可注入自定义 checks（key -> callable(value) -> bool）。"""

    def __init__(self, checks=None):
        self._checks = dict(DEFAULT_CHECKS)
        if checks:
            self._checks.update(checks)

    def __call__(self, state, run_id):
        if not isinstance(state, dict):
            return True
        spec = state.get("verify")
        if not spec:
            return True  # 无验证规格 → 放行（向后兼容）
        if not isinstance(spec, dict):
            _LOG.warning("auditor: verify 规格非 dict，跳过核查 run=%s", run_id)
            return True
        return self._verify(spec, run_id)

    def _verify(self, spec, run_id) -> bool:
        for kind, val in spec.items():
            check = self._checks.get(kind)
            if check is None:
                # 未知核查类型 → 不阻断（保守放行），仅告警
                _LOG.warning("auditor: 未知核查类型 %s，跳过 run=%s", kind, run_id)
                continue
            try:
                ok = bool(check(val))
            except Exception as e:  # noqa: BLE001
                _LOG.warning("auditor: 核查 %s 异常，视为失败: %s", kind, e)
                return False
            if not ok:
                _LOG.warning("auditor: 核查 %s 未通过 run=%s", kind, run_id)
                return False
        return True


def build_default_auditor() -> EnvironmentAuditor:
    """构造默认环境事实审计器（仅文件 / 日志等只读核查）。"""
    return EnvironmentAuditor()
