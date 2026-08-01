"""L6 虚实交互闭环 · 感知数据流网关 —— 完全自研核心（生命体OS 白皮书 L6）。

**问题**：L1 肉体层的感知源（STT / VLM / Crawl / Browser / 传感器）会把外部世界的原始数据
直接灌进内核。这条路是生命体**最大的攻击面与污染源**：提示词注入从这儿进、隐私泄露从这儿漏、
感知洪泛从这儿把主环压垮。白皮书画了 `L1A 感知` → 内核这条线，但中间**没有门**。

本模块就是那道门。**一切外部感知必须过网关**，六道工序，缺一不可：

| 序 | 工序 | 失败后果（没这道门会怎样） |
|----|------|---------------------------|
| 1 | 背压限流（令牌桶） | 感知洪泛打爆主环，生命体"癫痫" |
| 2 | 内容指纹去重 | 同一条爬虫结果反复进记忆，记忆被灌水 |
| 3 | 隐私脱敏（PII 掩码） | 手机号/身份证/银行卡进日志与记忆 → 宪法 privacy 破防 |
| 4 | 注入检测 | "忽略以上指令"直接改写生命体目标 → 灵魂被劫持 |
| 5 | 可信度分层 | 网页谣言与人类明示指令同权，垃圾进垃圾出 |
| 6 | 订阅分发 | 各层各拿各的，互相污染 |

**纪律**：
- 脱敏是**入口即做**，不是"存的时候再说"——原文不落任何持久层；
- 注入嫌疑**隔离但留档**（`quarantine`），不静默丢弃（理念6 诚实：拦了要说拦了什么）；
- 网关只降权不撒谎：可信度低的照样往下发，但 `trust` 字段如实标注，由下游决策。

诚实度：② 单元验证（tests/test_interact_layer.py）。接真实 STT/爬虫流为 ③ 待验。
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 来源可信度基线（理念6：量化置信，不给二元真假）
TRUST_TIERS: Dict[str, float] = {
    "human": 1.00,      # 人类明示输入
    "sensor": 0.90,     # 自有传感器（麦克风/摄像头/眼镜）
    "internal": 0.85,   # 内核自产（子粒子回报）
    "api": 0.70,        # 有契约的第三方 API
    "web": 0.40,        # 公开网页抓取
    "unknown": 0.20,    # 来路不明
}

# 隐私脱敏规则（中国大陆常见 PII；命中即掩码，原文不出网关）
_PII_RULES: List[tuple] = [
    ("id_card", re.compile(r"\b\d{17}[\dXx]\b")),
    ("bank_card", re.compile(r"\b\d{16,19}\b")),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
]

# 提示词注入 / 越权指令特征（大小写不敏感）
_INJECTION_PATTERNS: List[tuple] = [
    ("override_instruction", re.compile(
        r"(忽略(以上|之前|前面).{0,6}(指令|要求|设定)|ignore\s+(all\s+)?(previous|above)\s+instructions)",
        re.I)),
    ("role_hijack", re.compile(
        r"(你现在是|从现在起你是|you\s+are\s+now\s+a?)\s*", re.I)),
    # 中文语序两头都要防：「输出你的系统提示」与「把你的系统提示输出给我」
    ("prompt_exfil", re.compile(
        r"(泄露|输出|打印|复述|重复).{0,10}(系统提示|系统指令|系统prompt|prompt)"
        r"|(系统提示|系统指令|系统prompt).{0,10}(泄露|输出|打印|复述|重复|告诉|发给|给我|看看)"
        r"|reveal\s+your\s+(system\s+)?prompt"
        r"|(repeat|print|show)\s+(me\s+)?(the\s+|your\s+)?(system\s+)?prompt", re.I)),
    ("destructive_cmd", re.compile(
        r"(rm\s+-rf\s+/|drop\s+table|format\s+c:|del\s+/s\s+/q)", re.I)),
    ("credential_probe", re.compile(
        r"(api[_\s-]?key|secret[_\s-]?key|password|密钥|口令).{0,10}(是什么|告诉我|给我|发我)", re.I)),
]

ACCEPTED = "accepted"
RATE_LIMITED = "rate_limited"
DUPLICATE = "duplicate"
QUARANTINED = "quarantined"


@dataclass
class Percept:
    """网关出口的标准感知事件（下游只认这个结构）。"""
    pid: str
    source: str
    kind: str
    text: str                      # 已脱敏文本
    trust: float
    ts: float
    redactions: Dict[str, int] = field(default_factory=dict)   # 脱敏计数：类型→次数
    flags: List[str] = field(default_factory=list)             # 注入嫌疑等标记
    meta: Dict[str, Any] = field(default_factory=dict)
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {
            "pid": self.pid, "source": self.source, "kind": self.kind,
            "text": self.text, "trust": round(self.trust, 3), "ts": self.ts,
            "redactions": dict(self.redactions), "flags": list(self.flags),
            "fingerprint": self.fingerprint,
        }


@dataclass
class IngestResult:
    status: str
    reason: str = ""
    percept: Optional[Percept] = None

    @property
    def ok(self) -> bool:
        return self.status == ACCEPTED

    def to_dict(self) -> dict:
        return {"status": self.status, "reason": self.reason,
                "percept": self.percept.to_dict() if self.percept else None}


def redact(text: str) -> tuple:
    """PII 掩码。返回 (脱敏后文本, {类型: 命中次数})。"""
    counts: Dict[str, int] = {}
    out = text
    for name, pat in _PII_RULES:
        found = pat.findall(out)
        if found:
            counts[name] = counts.get(name, 0) + len(found)
            out = pat.sub(f"[{name}:已脱敏]", out)
    return out, counts


def detect_injection(text: str) -> List[str]:
    """返回命中的注入特征名列表（空列表 = 干净）。"""
    return [name for name, pat in _INJECTION_PATTERNS if pat.search(text)]


class PerceptionGateway:
    """感知数据流网关：限流 → 去重 → 脱敏 → 注入检测 → 定信 → 分发。"""

    RATE_LIMIT = 50           # 每秒最多接纳条数（令牌桶容量/速率）
    DEDUP_WINDOW = 300.0      # 指纹去重窗口（秒）
    QUARANTINE_KEEP = 200     # 隔离区保留条数上限
    INJECTION_TRUST_PENALTY = 0.5   # 命中注入特征的可信度打折

    def __init__(self, *, rate_limit: Optional[int] = None,
                 dedup_window: Optional[float] = None,
                 block_injection: bool = True) -> None:
        self.rate_limit = self.RATE_LIMIT if rate_limit is None else rate_limit
        self.dedup_window = self.DEDUP_WINDOW if dedup_window is None else dedup_window
        self.block_injection = block_injection
        self._tokens = float(self.rate_limit)
        self._last_refill: Optional[float] = None
        self._seen: Dict[str, float] = {}
        self._subs: Dict[str, List[Callable[[Percept], None]]] = {}
        self.quarantine: List[Dict[str, Any]] = []
        self.counters: Dict[str, int] = {ACCEPTED: 0, RATE_LIMITED: 0,
                                         DUPLICATE: 0, QUARANTINED: 0}
        self._seq = 0

    # ---------------- 订阅 ----------------

    def subscribe(self, kind: str, fn: Callable[[Percept], None]) -> None:
        """订阅某类感知；kind="*" 表示全订。"""
        self._subs.setdefault(kind, []).append(fn)

    def _dispatch(self, p: Percept) -> None:
        for fn in list(self._subs.get(p.kind, [])) + list(self._subs.get("*", [])):
            try:
                fn(p)
            except Exception:  # noqa: BLE001 —— 一个订阅者炸不能连累感知主链
                continue

    # ---------------- 限流 ----------------

    def _refill(self, now: float) -> None:
        if self._last_refill is None:
            self._last_refill = now
            return
        elapsed = max(0.0, now - self._last_refill)
        self._tokens = min(float(self.rate_limit), self._tokens + elapsed * self.rate_limit)
        self._last_refill = now

    def _take_token(self, now: float) -> bool:
        self._refill(now)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False

    # ---------------- 主入口 ----------------

    def ingest(self, source: str, kind: str, text: str, *,
               meta: Optional[Dict[str, Any]] = None,
               now: Optional[float] = None) -> IngestResult:
        ts = time.time() if now is None else now
        text = text or ""

        # 1) 背压限流
        if not self._take_token(ts):
            self.counters[RATE_LIMITED] += 1
            return IngestResult(RATE_LIMITED,
                                f"超过 {self.rate_limit} 条/秒，触发背压（保护主环不被感知洪泛压垮）")

        # 2) 指纹去重
        fp = hashlib.sha256(f"{source}|{kind}|{text}".encode("utf-8")).hexdigest()[:16]
        last = self._seen.get(fp)
        if last is not None and (ts - last) < self.dedup_window:
            self.counters[DUPLICATE] += 1
            return IngestResult(DUPLICATE, f"{self.dedup_window:.0f}s 内重复内容（指纹 {fp}）")
        self._seen[fp] = ts
        self._gc_seen(ts)

        # 3) 隐私脱敏（入口即做，原文不下传）
        clean, redactions = redact(text)

        # 4) 注入检测
        flags = detect_injection(clean)

        # 5) 可信度分层
        trust = TRUST_TIERS.get(source, TRUST_TIERS["unknown"])
        if flags:
            trust *= self.INJECTION_TRUST_PENALTY

        self._seq += 1
        p = Percept(pid=f"pc-{self._seq}", source=source, kind=kind, text=clean,
                    trust=trust, ts=ts, redactions=redactions, flags=flags,
                    meta=dict(meta or {}), fingerprint=fp)

        if flags and self.block_injection:
            self.counters[QUARANTINED] += 1
            self.quarantine.append({"percept": p.to_dict(), "flags": flags, "ts": ts})
            if len(self.quarantine) > self.QUARANTINE_KEEP:
                self.quarantine = self.quarantine[-self.QUARANTINE_KEEP:]
            return IngestResult(QUARANTINED,
                                f"命中注入特征 {flags}，已隔离留档（不静默丢弃）", p)

        # 6) 分发
        self.counters[ACCEPTED] += 1
        self._dispatch(p)
        return IngestResult(ACCEPTED, "", p)

    def _gc_seen(self, now: float) -> None:
        if len(self._seen) < 4096:
            return
        cutoff = now - self.dedup_window
        self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}

    # ---------------- 观测 ----------------

    def total(self) -> int:
        return sum(self.counters.values())

    def drop_rate(self) -> float:
        """被拒比例（限流+去重+隔离）。给紧急制动总线做过载信号。"""
        t = self.total()
        if t == 0:
            return 0.0
        return (t - self.counters[ACCEPTED]) / t

    def overloaded(self, threshold: float = 0.5, min_total: int = 20) -> bool:
        return self.total() >= min_total and self.drop_rate() >= threshold

    def stats(self) -> Dict[str, Any]:
        return {"counters": dict(self.counters), "total": self.total(),
                "drop_rate": round(self.drop_rate(), 4),
                "quarantined_kept": len(self.quarantine),
                "overloaded": self.overloaded()}
