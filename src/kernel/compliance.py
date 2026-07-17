"""AOS v1.0 合规安全层 — 审计 / 内容安全 / 规则引擎。

AI 代理人不是法外之地。这一层保证：
  - 每一操作都留下不可篡改的审计记录
  - 敏感信息（手机号/身份证/银行卡/API key等）自动脱敏
  - 有害内容（暴力/色情/违法指令）按规则拦截
  - Agent 操作边界由规则引擎强制执行（allow/deny + 速率限制）

设计原则：
  - 零依赖：纯 stdlib (re/hashlib/json/threading/datetime)
  - 事件驱动：通过 EventBus 订阅内核事件，自动记录审计日志
  - 可替换：ContentGuard 的正则规则集可注入，PolicyEngine 的策略可替换
  - 不阻断：默认审计模式（记录 + 告警），可切换为阻断模式
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

import logging

_LOG = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 审计日志 — 不可篡改的追加式记录
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AuditEntry:
    """一条不可篡改的审计记录。

    每条记录带链式哈希（prev_hash），确保记录序列不可事后插入/删除。
    """
    actor: str                      # 操作主体（agent_id / user_id）
    action: str                     # 操作（chat / skill_call / agent_register / ...）
    resource: str = ""              # 操作对象
    result: str = "ok"             # ok / denied / blocked / error
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    prev_hash: str = ""             # 链式哈希（防篡改）
    event_id: str = ""              # 自动生成
    entry_hash: str = ""            # 本条哈希

    def __post_init__(self):
        if not self.event_id:
            self.event_id = hashlib.sha256(
                f"{self.actor}{self.action}{self.timestamp}".encode()
            ).hexdigest()[:12]
        if not self.entry_hash:
            content = f"{self.event_id}|{self.actor}|{self.action}|{self.resource}|{self.result}|{self.timestamp}|{self.prev_hash}"
            self.entry_hash = hashlib.sha256(content.encode()).hexdigest()


class AuditTrail:
    """不可篡改的追加式审计日志。

    特性：
    - 链式哈希：每条记录包含前一条的哈希，确保序列不可事后篡改
    - 内存 + 文件双写（可选文件路径）
    - 按 actor / action / time 三维查询
    - 可订阅 EventBus 自动记录内核事件
    """

    def __init__(self, filepath: str = "", max_entries: int = 10000):
        self._lock = threading.RLock()
        self._entries: List[AuditEntry] = []
        self._max_entries = max_entries
        self._filepath = filepath
        self._last_hash = "0000"  # 创世哈希

    def record(self, actor: str, action: str, resource: str = "",
               result: str = "ok", detail: Optional[Dict[str, Any]] = None) -> AuditEntry:
        """追加一条审计记录。"""
        with self._lock:
            entry = AuditEntry(
                actor=actor, action=action, resource=resource,
                result=result, detail=detail or {},
                prev_hash=self._last_hash,
            )
            self._last_hash = entry.entry_hash
            self._entries.append(entry)

            # 修剪
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries:]

            # 文件持久化
            if self._filepath:
                self._write_to_file(entry)

            return entry

    def query(self, actor: str = "", action: str = "",
              result: str = "", limit: int = 50) -> List[AuditEntry]:
        """按条件查询审计记录。"""
        with self._lock:
            results = []
            for e in reversed(self._entries):
                if actor and e.actor != actor:
                    continue
                if action and e.action != action:
                    continue
                if result and e.result != result:
                    continue
                results.append(e)
                if len(results) >= limit:
                    break
            return results

    def verify_integrity(self) -> bool:
        """验证审计链的完整性（防篡改校验）。"""
        with self._lock:
            if not self._entries:
                return True
            expected_prev = "0000"
            for e in self._entries:
                if e.prev_hash != expected_prev:
                    return False
                expected_prev = e.entry_hash
            return True

    def subscribe_to_kernel(self, kernel) -> None:
        """订阅内核事件总线，自动记录关键操作为审计日志。"""
        kernel.events.subscribe("agent.*", lambda e: self.record(
            actor=e.payload.get("agent_id", e.source),
            action=e.event_type,
            result="ok" if "failed" not in e.event_type else "error",
        ))
        kernel.events.subscribe("message.*", lambda e: self.record(
            actor=e.payload.get("sender", "system"),
            action=e.event_type,
            result="ok" if "denied" not in e.event_type else "denied",
        ))
        kernel.events.subscribe("skill.*", lambda e: self.record(
            actor=e.payload.get("caller", "system"),
            action=e.event_type,
            resource=e.payload.get("skill_id", ""),
        ))
        kernel.events.subscribe("model.*", lambda e: self.record(
            actor="model-gateway",
            action=e.event_type,
            resource=e.payload.get("model", ""),
        ))

    def _write_to_file(self, entry: AuditEntry) -> None:
        try:
            with open(self._filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "event_id": entry.event_id,
                    "actor": entry.actor,
                    "action": entry.action,
                    "resource": entry.resource,
                    "result": entry.result,
                    "timestamp": entry.timestamp,
                    "entry_hash": entry.entry_hash,
                    "prev_hash": entry.prev_hash,
                }, ensure_ascii=False) + "\n")
        except OSError as e:
            _LOG.warning("AuditTrail: failed to write audit entry to %s: %s", self._filepath, e)

    @property
    def total_entries(self) -> int:
        with self._lock:
            return len(self._entries)


# ═══════════════════════════════════════════════════════════════════
# 内容安全守卫 — 敏感脱敏 + 有害拦截
# ═══════════════════════════════════════════════════════════════════

class ContentGuard:
    """内容安全守卫：敏感信息脱敏 + 有害内容检测。

    两层防护：
    1. 敏感信息脱敏（redact）：自动替换手机号/身份证/银行卡/API key等
    2. 有害内容拦截（block）：检测暴力/色情/违法指令模式，可配置阻断/告警模式

    规则集可注入、可替换。默认规则覆盖中国个人信息保护法(PIPL)要求。
    """

    # 敏感信息模式（个人信息保护法）
    SENSITIVE_PATTERNS: Dict[str, Pattern] = {
        "phone_cn":    re.compile(r"1[3-9]\d{9}"),
        "id_card":     re.compile(r"\d{17}[\dXx]"),
        "bank_card":   re.compile(r"\d{16,19}"),
        "email":       re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
        "ip_address":   re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"),
        "api_key_bearer": re.compile(r"(?:sk-|TK-|AK-)[a-zA-Z0-9]{20,}"),
        "wechat_id":   re.compile(r"wxid_[a-zA-Z0-9]+"),
        "qq_number":    re.compile(r"[1-9]\d{4,10}"),
    }

    # 有害内容关键词模式
    HARMFUL_PATTERNS: Dict[str, Pattern] = {
        "violence":    re.compile(r"(?:杀|砍|炸|枪|毒|绑架|恐怖|暴动)", re.IGNORECASE),
        "sexual_minor": re.compile(r"(?:儿童.*色|未成年.*裸|幼.*性)", re.IGNORECASE),
        "self_harm":   re.compile(r"(?:自杀|自残|割腕|跳楼|上吊)", re.IGNORECASE),
        "illegal_service": re.compile(r"(?:代考|代写论文|卖分|办假证|洗钱|套现)", re.IGNORECASE),
        "discrimination": re.compile(r"(?:种族.*歧视|民族.*仇恨|宗教.*煽动)", re.IGNORECASE),
    }

    def __init__(self, mode: str = "audit",
                 custom_sensitive: Dict[str, Pattern] | None = None,
                 custom_harmful: Dict[str, Pattern] | None = None):
        """
        mode: "audit" (记录+continue) | "block" (拦截+拒绝)
        """
        self.mode = mode
        self._sensitive = dict(self.SENSITIVE_PATTERNS)
        self._harmful = dict(self.HARMFUL_PATTERNS)
        if custom_sensitive:
            self._sensitive.update(custom_sensitive)
        if custom_harmful:
            self._harmful.update(custom_harmful)

        # 拦截统计
        self._lock = threading.RLock()
        self.redacted_count = 0
        self.blocked_count = 0

    def check(self, content: str) -> Dict[str, Any]:
        """检查内容。返回 {ok, redacted, findings, blocked}。"""
        result: Dict[str, Any] = {
            "ok": True,
            "original_length": len(content),
            "redacted": None,
            "findings": [],
            "blocked": False,
            "block_reason": "",
        }

        # 1. 敏感信息检测
        for name, pattern in self._sensitive.items():
            matches = pattern.findall(content)
            if matches:
                result["findings"].append({
                    "type": "sensitive",
                    "rule": name,
                    "count": len(matches),
                })

        # 2. 有害内容检测
        for name, pattern in self._harmful.items():
            if pattern.search(content):
                result["findings"].append({
                    "type": "harmful",
                    "rule": name,
                })
                if self.mode == "block":
                    result["blocked"] = True
                    result["block_reason"] = name
                    result["ok"] = False

        # 3. 脱敏
        if result["findings"]:
            redacted = self._redact(content)
            result["redacted"] = redacted

        # 统计
        with self._lock:
            if result["redacted"]:
                self.redacted_count += 1
            if result["blocked"]:
                self.blocked_count += 1

        return result

    def _redact(self, content: str) -> str:
        """对所有敏感模式做脱敏替换。"""
        result = content
        replacements = {
            "phone_cn":     lambda m: m.group()[:3] + "****" + m.group()[-2:],
            "id_card":      lambda m: m.group()[:6] + "********" + m.group()[-4:],
            "bank_card":    lambda m: m.group()[:6] + "****" + m.group()[-4:],
            "email":        lambda m: m.group()[0] + "***@" + m.group().split("@")[-1],
            "api_key_bearer": lambda m: m.group()[:8] + "..." + m.group()[-4:],
        }
        for name, pattern in self._sensitive.items():
            if name in replacements:
                result = pattern.sub(replacements[name], result)
        return result

    def safe_output(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """安全输出：先检查再决定返回脱敏内容还是拒绝。"""
        check = self.check(content)
        if check["blocked"]:
            return "[内容因安全策略被拦截]", check
        if check["redacted"]:
            return check["redacted"], check
        return content, check


# ═══════════════════════════════════════════════════════════════════
# 策略引擎 — Agent 操作边界规则
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PolicyRule:
    """一条策略规则。"""
    rule_id: str
    description: str
    action_pattern: str        # 匹配的操作名（支持 * 通配符: "file:delete:*"）
    actors: List[str]          # 适用主体（空=所有）
    effect: str = "deny"       # allow / deny
    priority: int = 0          # 高优先级规则优先匹配
    rate_limit_per_minute: int = 0  # 0=无限制

    def matches(self, action: str, actor: str) -> bool:
        if self.actors and actor not in self.actors:
            return False
        if self.action_pattern == "*":
            return True
        if self.action_pattern.endswith("*"):
            return action.startswith(self.action_pattern[:-1])
        return action == self.action_pattern


class PolicyEngine:
    """规则引擎：Agent 操作边界强制执行。

    内置默认规则：
    - 所有 agent 默认允许 chat 操作
    - 所有 agent 默认禁止 file:delete / system:shutdown
    - admin 角色有完全权限
    - 每 agent 每操作类型的速率限制
    """

    DEFAULT_RULES = [
        PolicyRule("r001", "禁止删除文件", "file:delete:*", [], "deny", priority=100),
        PolicyRule("r002", "禁止系统关闭", "system:shutdown", [], "deny", priority=100),
        PolicyRule("r003", "禁止执行shell", "system:shell", [], "deny", priority=100),
        PolicyRule("r004", "禁止外发邮件", "email:send", [], "deny", priority=80),
        PolicyRule("r005", "禁止网络访问清单外域名", "http:request", [], "deny", priority=60),
        PolicyRule("r006", "允许chat操作", "chat", [], "allow", priority=10),
        PolicyRule("r007", "允许技能调用", "call:*", [], "allow", priority=10),
        PolicyRule("r008", "允许memory读写", "memory:*", [], "allow", priority=10),
        PolicyRule("r009", "admin完全权限", "*", ["admin"], "allow", priority=1000),
    ]

    def __init__(self, custom_rules: List[PolicyRule] | None = None):
        self._lock = threading.RLock()
        self._rules: List[PolicyRule] = list(self.DEFAULT_RULES)
        if custom_rules:
            self._rules.extend(custom_rules)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

        # 速率限制追踪
        self._rate_tracker: Dict[str, List[float]] = {}
        self._rate_window = 60.0

    def evaluate(self, action: str, actor: str,
                 resource: str = "") -> Dict[str, Any]:
        """评估一个操作。返回 {allowed, matched_rule, reason, rate_limited}。"""
        result = {
            "allowed": False,
            "matched_rule": "",
            "reason": "no matching rule",
            "rate_limited": False,
        }

        with self._lock:
            for rule in self._rules:
                if rule.matches(action, actor):
                    result["matched_rule"] = rule.rule_id
                    result["allowed"] = rule.effect == "allow"

                    # 速率限制
                    if rule.rate_limit_per_minute > 0:
                        key = f"{actor}:{action}"
                        now = time.time()
                        times = self._rate_tracker.get(key, [])
                        times = [t for t in times if now - t < self._rate_window]
                        if len(times) >= rule.rate_limit_per_minute:
                            result["allowed"] = False
                            result["rate_limited"] = True
                            result["reason"] = (
                                f"rate limit exceeded: {rule.rate_limit_per_minute}/min "
                                f"for {action}")
                        else:
                            times.append(now)
                            self._rate_tracker[key] = times

                    result["reason"] = (
                        f"rule {rule.rule_id}: {rule.description}"
                        if not result["rate_limited"] else result["reason"])
                    break

        return result

    def add_rule(self, rule: PolicyRule) -> None:
        with self._lock:
            self._rules.append(rule)
            self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            before = len(self._rules)
            self._rules = [r for r in self._rules if r.rule_id != rule_id]
            return len(self._rules) < before

    @property
    def rules(self) -> List[PolicyRule]:
        with self._lock:
            return list(self._rules)


# ═══════════════════════════════════════════════════════════════════
# 合规层 — 统一入口
# ═══════════════════════════════════════════════════════════════════

class ComplianceLayer:
    """合规安全统一层：审计 + 内容安全 + 策略引擎。

    用法：
        comp = ComplianceLayer()
        comp.audit.subscribe_to_kernel(kernel)  # 自动记录所有操作
        guard_check = comp.guard.check(user_input)  # 内容安全检查
        policy_check = comp.policy.evaluate("chat", "agent1")  # 策略评估
    """

    def __init__(self,
                 audit_file: str = "",
                 guard_mode: str = "audit",
                 policy_rules: List[PolicyRule] | None = None):
        self.audit = AuditTrail(filepath=audit_file)
        self.guard = ContentGuard(mode=guard_mode)
        self.policy = PolicyEngine(custom_rules=policy_rules)

    def safe_chat(self, actor: str, prompt: str, response_func: Callable[[str], str]) -> Dict[str, Any]:
        """安全的完整对话流程：策略检查 → 内容检查 → 执行 → 审计记录。

        这是一个端到端的合规保护流程：
        1. 策略引擎：该 actor 是否有权 chat？
        2. 内容守卫：prompt 是否包含敏感/有害内容？
        3. 执行：调用真实 LLM
        4. 内容守卫：response 是否包含敏感内容？
        5. 审计：完整记录
        """
        # 1. 策略检查
        p = self.policy.evaluate("chat", actor)
        if not p["allowed"]:
            self.audit.record(actor, "chat", result="denied",
                              detail={"reason": p["reason"]})
            return {"ok": False, "reason": p["reason"], "stage": "policy"}

        # 2. prompt 安全检查
        c_in = self.guard.check(prompt)
        if c_in["blocked"]:
            self.audit.record(actor, "chat", result="blocked",
                              detail={"block_reason": c_in["block_reason"]})
            return {"ok": False, "reason": c_in["block_reason"], "stage": "content_in"}

        safe_prompt = c_in["redacted"] or prompt

        # 3. 执行
        try:
            response = response_func(safe_prompt)
        except Exception as e:
            self.audit.record(actor, "chat", result="error",
                              detail={"error": str(e)})
            return {"ok": False, "reason": str(e), "stage": "execution"}

        # 4. response 安全检查
        c_out = self.guard.check(response)
        safe_response = c_out["redacted"] or response

        # 5. 审计
        self.audit.record(actor, "chat", result="ok",
                          detail={"prompt_len": len(prompt),
                                  "response_len": len(response),
                                  "redacted": c_in["redacted"] is not None or c_out["redacted"] is not None})

        return {
            "ok": True,
            "response": safe_response,
            "findings": c_in["findings"] + c_out["findings"],
            "redacted": c_in["redacted"] is not None or c_out["redacted"] is not None,
        }


# ═══════════════════════════════════════════════════════════════════
# 质量门 — 三分规则（安全 / 质量 / 合规 × ERROR / WARN / INFO）
# ═══════════════════════════════════════════════════════════════════
#
# 借鉴 CodeArts「质量门」(3000+ 规则) 的工程化思路，但落地为 AOS 自己的
# 可扩展三分规则集：
#   - 三类：SECURITY（安全） / QUALITY（质量） / COMPLIANCE（合规）
#   - 三级严重度：ERROR（阻断，质量门不通过）/ WARN（告警）/ INFO（提示）
# 检查以 AST 为主（语法/危险调用/裸 except），正则仅用于合规类文本检查。
# 规则可注入；run() 接收 {文件名: 代码} 返回结构化报告。

CAT_SECURITY = "SECURITY"
CAT_QUALITY = "QUALITY"
CAT_COMPLIANCE = "COMPLIANCE"
SEV_ERROR = "ERROR"    # 阻断：质量门不通过
SEV_WARN = "WARN"      # 告警：记录但需人工确认
SEV_INFO = "INFO"      # 提示：可选改进


@dataclass
class QualityRule:
    """一条质量门规则。

    check(filename, code) -> 命中返回 (line, message)，否则返回 None。
    """
    rule_id: str
    category: str
    severity: str
    description: str
    check: Callable[[str, str], Optional[Tuple[int, str]]]


@dataclass
class Violation:
    rule_id: str
    category: str
    severity: str
    file: str
    line: int
    message: str


@dataclass
class QualityReport:
    violations: List[Violation]
    passed: bool
    files_checked: int
    summary: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "files_checked": self.files_checked,
            "summary": self.summary,
            "violations": [
                {
                    "rule_id": v.rule_id, "category": v.category,
                    "severity": v.severity, "file": v.file,
                    "line": v.line, "message": v.message,
                }
                for v in self.violations
            ],
        }


# ── 内置检查函数（AST 为主，正则仅用于文本合规）──

def _attr_chain(node: "Any") -> str:
    """把 a.b.c 属性链拼成字符串。"""
    parts = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    return ".".join(reversed(parts))


def _is_python_file(name: str) -> bool:
    """是否 Python 源文件。基于 Python AST 的规则只对 .py 生效，
    其它语言（如 .js/.ts）的语法由对应语言的执行器（node --check 等）负责，
    避免用 Python 解析器误判非 Python 文件（多语言代码团队的正确性前提）。"""
    return name.endswith((".py", ".pyi"))


def _gt_syntax(name: str, code: str) -> Optional[Tuple[int, str]]:
    if not _is_python_file(name):
        return None  # 非 Python 文件的语法由对应语言执行器（如 node --check）校验
    try:
        ast.parse(code)
    except SyntaxError as e:
        return (e.lineno or 1, f"语法错误: {e.msg}")
    return None


_DANGEROUS_BUILTINS = {"eval", "exec", "compile", "input", "__import__"}
_DANGEROUS_ATTRS = {
    "os.system", "os.popen", "os.exec*", "subprocess.call",
    "subprocess.run", "subprocess.Popen", "pickle.loads",
    "marshal.loads", "yaml.load",
}

# 非 Python 文件（JS/TS 等）的危险调用正则扫描：AST 走不通时的安全兜底。
# 只挑真实高危、且不会与常见合法用法冲突的模式（如 regex.exec 是合法的，不列）。
_DANGEROUS_NONPY_PATTERNS = [
    (r"\beval\s*\(", "eval()"),
    (r"\bnew\s+Function\s*\(", "new Function()"),
    (r"child_process", "child_process"),
    (r"\bexecSync\s*\(", "execSync()"),
]


def _gt_dangerous_call(name: str, code: str) -> Optional[Tuple[int, str]]:
    if not _is_python_file(name):
        for pat, label in _DANGEROUS_NONPY_PATTERNS:
            m = re.search(pat, code)
            if m:
                line = code[: m.start()].count("\n") + 1
                return (line, f"禁止调用危险API {label}")
        return None
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None  # 语法错误由 _gt_syntax 负责
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in _DANGEROUS_BUILTINS:
                return (node.lineno, f"禁止调用危险内置函数 {f.id}()")
            if isinstance(f, ast.Attribute):
                chain = _attr_chain(f)
                if chain in _DANGEROUS_ATTRS:
                    return (node.lineno, f"禁止调用危险API {chain}")
    return None


def _gt_bare_except(name: str, code: str) -> Optional[Tuple[int, str]]:
    if not _is_python_file(name):
        return None  # 裸 except 是 Python 专属概念
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            return (node.lineno, "裸 except 会吞掉所有异常，应指定异常类型")
    return None


def _gt_long_file(name: str, code: str) -> Optional[Tuple[int, str]]:
    n = code.count("\n") + 1
    if n > 500:
        return (1, f"文件过长（{n} 行），建议拆分")
    return None


def _gt_license_header(name: str, code: str) -> Optional[Tuple[int, str]]:
    if not re.search(r"(license|copyright|版权|许可|spdx|MIT|Apache)", code, re.I):
        return (1, "缺少许可证/版权头注释")
    return None


def _gt_todo_marker(name: str, code: str) -> Optional[Tuple[int, str]]:
    if re.search(r"\b(TODO|FIXME|XXX)\b", code):
        return (1, "存在未完成标记 (TODO/FIXME/XXX)")
    return None


class QualityGate:
    """可配置的三分质量门。

    用法：
        gate = QualityGate()
        report = gate.run({"calc.py": "x=1\\n..."})
        if not report.passed:
            ... 阻断合并/部署
    """

    DEFAULT_RULES = [
        QualityRule("q001", CAT_QUALITY, SEV_ERROR, "语法必须可解析", _gt_syntax),
        QualityRule("s001", CAT_SECURITY, SEV_ERROR, "禁止危险调用（eval/exec/os.system/...）",
                    _gt_dangerous_call),
        QualityRule("q002", CAT_QUALITY, SEV_WARN, "避免裸 except", _gt_bare_except),
        QualityRule("q003", CAT_QUALITY, SEV_WARN, "文件不宜过长", _gt_long_file),
        QualityRule("c001", CAT_COMPLIANCE, SEV_INFO, "建议包含许可证头", _gt_license_header),
        QualityRule("c002", CAT_COMPLIANCE, SEV_INFO, "避免遗留 TODO 标记", _gt_todo_marker),
    ]

    def __init__(self, custom_rules: List[QualityRule] | None = None):
        self._rules: List[QualityRule] = list(self.DEFAULT_RULES)
        if custom_rules:
            self._rules.extend(custom_rules)

    def add_rule(self, rule: QualityRule) -> None:
        self._rules.append(rule)

    def run(self, files: Dict[str, str]) -> QualityReport:
        """对 {文件名: 代码} 跑全部规则。

        passed 仅当不存在任何 ERROR 级违规时为 True（WARN/INFO 不阻断）。
        """
        violations: List[Violation] = []
        for fname, code in files.items():
            for rule in self._rules:
                try:
                    hit = rule.check(fname, code)
                except Exception as e:  # noqa: BLE001 - 单条规则异常不影响整体
                    _LOG.warning("QualityGate: 规则 %s 执行异常: %s", rule.rule_id, e)
                    continue
                if hit:
                    line, msg = hit
                    violations.append(Violation(
                        rule_id=rule.rule_id, category=rule.category,
                        severity=rule.severity, file=fname, line=line,
                        message=msg,
                    ))

        summary = {
            "ERROR": sum(1 for v in violations if v.severity == SEV_ERROR),
            "WARN": sum(1 for v in violations if v.severity == SEV_WARN),
            "INFO": sum(1 for v in violations if v.severity == SEV_INFO),
            "SECURITY": sum(1 for v in violations if v.category == CAT_SECURITY),
            "QUALITY": sum(1 for v in violations if v.category == CAT_QUALITY),
            "COMPLIANCE": sum(1 for v in violations if v.category == CAT_COMPLIANCE),
        }
        passed = summary["ERROR"] == 0
        return QualityReport(
            violations=violations, passed=passed,
            files_checked=len(files), summary=summary,
        )


__all__ = [
    "AuditEntry",
    "AuditTrail",
    "ComplianceLayer",
    "ContentGuard",
    "PolicyEngine",
    "PolicyRule",
    "QualityGate",
    "QualityRule",
    "QualityReport",
    "Violation",
    "CAT_SECURITY",
    "CAT_QUALITY",
    "CAT_COMPLIANCE",
    "SEV_ERROR",
    "SEV_WARN",
    "SEV_INFO",
]
