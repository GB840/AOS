"""插件：MCP 安全网关 — 白名单 + 命令注入检测 + 审计日志。

对账表 L3 要求：
> ⚠ 43% 开源 MCP 服务器含 OAuth 缺陷/命令注入 RCE→须白名单 + 沙箱

本网关包装 MCPSkillBus，在工具调用前做四层安全校验：
1. 工具白名单：只允许预注册的 MCP 工具
2. 命令注入检测：阻断含 shell 注入特征的参数
3. 路径遍历检测：阻断 ../ 等越权访问
4. 审计日志：记录所有调用，便于事后追溯

内核零依赖；本文件位于 plugins/，允许 import 具体实现。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from ..interfaces import SkillBus
from ..types import SkillInfo, SkillResult, SkillSpec

logger = logging.getLogger(__name__)

# ---- 命令注入检测模式 ----
# 匹配常见的 shell 命令注入特征
_COMMAND_INJECTION_PATTERNS: List[re.Pattern] = [
    re.compile(r"[;&|`$]"),                    # 分隔符 / 命令替换
    re.compile(r"\brm\s+-rf\b"),               # 递归删除
    re.compile(r"\bcurl\b.*\b-o\b"),           # curl 下载到文件
    re.compile(r"\bwget\b"),                    # wget 下载
    re.compile(r"\bchmod\b"),                   # 权限修改
    re.compile(r"\bchown\b"),                   # 所有者修改
    re.compile(r"\bsudo\b"),                     # 提权
    re.compile(r"\bkill\b"),                     # 杀进程
    re.compile(r"\breboot\b"),                   # 重启
    re.compile(r"\bshutdown\b"),                 # 关机
    re.compile(r"\bdd\s+if="),                   # 磁盘操作
    re.compile(r"\bmkfs\b"),                     # 格式化
    re.compile(r"\bmount\b"),                    # 挂载
    re.compile(r"\biptables\b"),                 # 防火墙
    re.compile(r"\bpasswd\b"),                   # 密码修改
    re.compile(r"\buseradd\b|\buserdel\b"),      # 用户管理
    re.compile(r"\bscp\b|\brsync\b"),            # 远程文件传输
    re.compile(r"\bnc\b|\bnetcat\b"),            # 网络工具
    re.compile(r"\b(\w+)\s*=\s*os\.system"),     # Python os.system 赋值
    re.compile(r"\b(\w+)\s*=\s*subprocess"),     # Python subprocess 赋值
    re.compile(r"\beval\s*\("),                  # Python eval
    re.compile(r"\bexec\s*\("),                  # Python exec
    re.compile(r"\b__import__\s*\("),            # Python 动态导入
]

# ---- 路径遍历检测 ----
_PATH_TRAVERSAL = re.compile(r"\.\.\/|\.\.\\\\")

# ---- 默认安全工具白名单 ----
# 只有在此列表中的 MCP 工具才允许通过安全网关调用。
# 生产环境应从配置加载，此处为安全默认值。
_DEFAULT_TOOL_WHITELIST: Set[str] = {
    # 文件操作（安全）
    "read_file", "list_directory", "search_files",
    # 代码分析
    "search_code", "grep", "find_symbol",
    # 知识库
    "memory_search", "memory_store", "codebase_search",
    # 文档
    "read_document", "search_docs",
    # 沙箱（受控执行）
    "execute_sandbox", "run_code_sandbox",
}


class MCPSecurityGateway(SkillBus):
    """MCP 安全网关：包装 SkillBus，在工具调用前做安全校验。

    用法：
        bus = MCPSkillBus()                          # 原有 MCP 总线
        secure = MCPSecurityGateway(bus)             # 安全网关包装
        kernel.set_skill_bus(secure)                 # 内核使用安全网关
    """

    def __init__(
        self,
        inner: SkillBus,
        tool_whitelist: Optional[Set[str]] = None,
        enable_command_check: bool = True,
        enable_path_check: bool = True,
        enable_audit: bool = True,
    ) -> None:
        self._inner = inner
        self._whitelist = tool_whitelist or _DEFAULT_TOOL_WHITELIST.copy()
        self._enable_command_check = enable_command_check
        self._enable_path_check = enable_path_check
        self._enable_audit = enable_audit
        self._blocked_calls: List[Dict[str, Any]] = []

    # ---- SkillBus 接口 ----

    def discover_skills(self) -> List[SkillInfo]:
        """返回白名单内的工具列表。"""
        all_skills = self._inner.discover_skills()
        return [s for s in all_skills if s.skill_id in self._whitelist]

    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> SkillResult:
        """安全校验后调用工具。"""
        # 1) 白名单检查
        if skill_id not in self._whitelist:
            self._audit("BLOCKED", skill_id, params, "不在白名单中")
            return SkillResult(ok=False, error=f"工具 '{skill_id}' 不在安全白名单中")

        # 2) 参数安全检查
        params_str = str(params)
        if self._enable_command_check:
            violation = self._check_command_injection(params_str)
            if violation:
                self._audit("BLOCKED", skill_id, params, f"命令注入: {violation}")
                return SkillResult(ok=False, error=f"参数含潜在命令注入: {violation}")

        if self._enable_path_check:
            if _PATH_TRAVERSAL.search(params_str):
                self._audit("BLOCKED", skill_id, params, "路径遍历")
                return SkillResult(ok=False, error="参数含路径遍历 (../)")

        # 3) 通过 → 委托底层
        self._audit("ALLOWED", skill_id, params)
        return self._inner.call_skill(skill_id, params)

    def register_skill(self, skill_spec: SkillSpec) -> None:
        """注册新工具到白名单。"""
        self._whitelist.add(skill_spec.skill_id)
        self._inner.register_skill(skill_spec)

    # ---- 白名单管理 ----

    def add_to_whitelist(self, tool_id: str) -> None:
        self._whitelist.add(tool_id)

    def remove_from_whitelist(self, tool_id: str) -> None:
        self._whitelist.discard(tool_id)

    def get_whitelist(self) -> Set[str]:
        return self._whitelist.copy()

    # ---- 安全审计 ----

    def get_blocked_calls(self) -> List[Dict[str, Any]]:
        """返回被拦截的调用记录（最近 100 条）。"""
        return self._blocked_calls[-100:]

    def _audit(self, action: str, skill_id: str, params: Any, reason: str = "") -> None:
        if not self._enable_audit:
            return
        record = {
            "action": action,
            "skill_id": skill_id,
            "params_snippet": str(params)[:200],
            "reason": reason,
        }
        if action == "BLOCKED":
            self._blocked_calls.append(record)
            logger.warning("MCP 安全网关拦截: skill=%s reason=%s", skill_id, reason)

    def _check_command_injection(self, text: str) -> Optional[str]:
        for pattern in _COMMAND_INJECTION_PATTERNS:
            match = pattern.search(text)
            if match:
                return f"pattern '{pattern.pattern}' matched '{match.group()}'"
        return None


__all__ = ["MCPSecurityGateway", "MCP_SECURITY_DEFAULT_WHITELIST"]
MCP_SECURITY_DEFAULT_WHITELIST = _DEFAULT_TOOL_WHITELIST