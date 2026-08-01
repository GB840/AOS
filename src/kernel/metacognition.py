"""L2F 元认知自省内核 —— 完全自研核心（生命体OS 白皮书 L2F）。

「知道自己不知道」的工程化。它不产生答案，只对**自己的思考过程**下判断：

1. 置信标定（calibration）：把主观自信与真实证据强度对齐，戳破「嘴硬」。
2. 循环检测（loop detection）：识别原地打转（同一动作重复、同一错误复现）。
3. 知识边界（epistemic gap）：识别「证据不足以支撑结论」并要求补证据。
4. 自省结论 → 直接给 autopilot 的**指令**：continue / gather_more / reflect / abort。

这是对 AGENTS.md §1.2.5「反思闭环」的前置守门员：
反思是「失败后怎么改」，元认知是「失败前就发现自己在瞎跑」。
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

# 拒答 / 空话特征（真实出现在 LLM 输出里的模式）
HEDGE_PATTERNS = (
    "作为一个ai", "作为ai", "我无法", "抱歉，我不能", "对不起，我不能",
    "i cannot", "i'm unable", "as an ai", "i apologize",
)
VAGUE_PATTERNS = ("可能", "也许", "大概", "应该是", "似乎", "或许",
                  "maybe", "perhaps", "probably", "might be")

VERDICT_CONTINUE = "continue"
VERDICT_GATHER = "gather_more"
VERDICT_REFLECT = "reflect"
VERDICT_ABORT = "abort"


@dataclass
class Introspection:
    verdict: str
    confidence: float             # 标定后的置信 0..1
    claimed_confidence: float     # 自称的置信
    reasons: List[str] = field(default_factory=list)
    looping: bool = False
    evidence_score: float = 0.0

    @property
    def overconfident(self) -> bool:
        return self.claimed_confidence - self.confidence > 0.25

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "confidence": round(self.confidence, 4),
                "claimed_confidence": round(self.claimed_confidence, 4),
                "overconfident": self.overconfident, "looping": self.looping,
                "evidence_score": round(self.evidence_score, 4),
                "reasons": list(self.reasons)}


class Metacognition:
    """元认知自省内核。无状态推理 + 有状态的循环记忆。"""

    def __init__(self, loop_window: int = 6, loop_repeat: int = 3,
                 min_evidence: float = 0.35):
        self.loop_window = loop_window
        self.loop_repeat = loop_repeat
        self.min_evidence = min_evidence
        self._fingerprints: List[str] = []
        self._errors: List[str] = []

    # ------------------------------------------------------------ 循环检测
    @staticmethod
    def _fingerprint(action: str, args: Optional[dict] = None) -> str:
        raw = f"{action}|{sorted((args or {}).items())}"
        return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:12]

    def record_action(self, action: str, args: Optional[dict] = None) -> None:
        self._fingerprints.append(self._fingerprint(action, args))
        if len(self._fingerprints) > self.loop_window * 4:
            self._fingerprints = self._fingerprints[-self.loop_window * 4:]

    def record_error(self, err: str) -> None:
        self._errors.append((err or "").strip()[:200])
        if len(self._errors) > self.loop_window * 4:
            self._errors = self._errors[-self.loop_window * 4:]

    def detect_loop(self) -> bool:
        """近 loop_window 步内同一动作出现 ≥ loop_repeat 次，或同一错误复现 ≥ 2 次。"""
        recent = self._fingerprints[-self.loop_window:]
        if recent and Counter(recent).most_common(1)[0][1] >= self.loop_repeat:
            return True
        errs = self._errors[-self.loop_window:]
        return bool(errs) and Counter(errs).most_common(1)[0][1] >= 2

    # ------------------------------------------------------------ 证据打分
    @staticmethod
    def evidence_score(text: str = "", *, sources: int = 0, exit_code: Optional[int] = None,
                       bytes_written: int = 0, search_hits: int = 0) -> float:
        """真实证据强度（不是模型自称）：来源数/退出码/落盘字节/检索命中。"""
        score = 0.0
        if sources > 0:
            score += min(0.3, 0.1 * sources)
        if search_hits > 0:
            score += min(0.25, 0.05 * search_hits)
        if exit_code == 0:
            score += 0.25
        elif exit_code not in (None, 0):
            score -= 0.15
        if bytes_written > 0:
            score += min(0.2, bytes_written / 5000.0)
        t = (text or "").strip()
        if len(t) >= 200:
            score += 0.1
        low = t.lower()
        if any(p in low for p in HEDGE_PATTERNS):
            score -= 0.35                     # 拒答话术直接扣穿
        vague = sum(1 for p in VAGUE_PATTERNS if p in low)
        score -= min(0.2, 0.04 * vague)
        if re.search(r"https?://", t):
            score += 0.05
        return max(0.0, min(1.0, round(score, 4)))

    # ------------------------------------------------------------ 自省
    def introspect(self, *, text: str = "", claimed_confidence: float = 0.8,
                   sources: int = 0, exit_code: Optional[int] = None,
                   bytes_written: int = 0, search_hits: int = 0,
                   step_index: int = 0, max_steps: int = 20) -> Introspection:
        ev = self.evidence_score(text, sources=sources, exit_code=exit_code,
                                 bytes_written=bytes_written, search_hits=search_hits)
        looping = self.detect_loop()
        reasons: List[str] = []

        # 标定：真实置信被证据强度封顶（自信不能超过证据）
        calibrated = min(float(claimed_confidence), 0.15 + 0.85 * ev)
        if looping:
            calibrated *= 0.5
            reasons.append("检测到原地打转（重复动作/重复错误）")
        if ev < self.min_evidence:
            reasons.append(f"证据强度 {ev:.2f} < 下限 {self.min_evidence:.2f}")
        if claimed_confidence - calibrated > 0.25:
            reasons.append(f"自称置信 {claimed_confidence:.2f} 明显高于证据支撑 {calibrated:.2f}")

        # 判决
        if looping:
            verdict = VERDICT_REFLECT
        elif ev <= 0.05:
            verdict = VERDICT_ABORT if step_index >= max_steps - 1 else VERDICT_GATHER
            reasons.append("几乎无有效证据")
        elif ev < self.min_evidence:
            verdict = VERDICT_GATHER
        else:
            verdict = VERDICT_CONTINUE
            reasons.append("证据充分，可继续")

        return Introspection(verdict=verdict, confidence=round(calibrated, 4),
                             claimed_confidence=float(claimed_confidence),
                             reasons=reasons, looping=looping, evidence_score=ev)

    def reset(self) -> None:
        self._fingerprints.clear()
        self._errors.clear()


__all__ = ["Metacognition", "Introspection", "VERDICT_CONTINUE", "VERDICT_GATHER",
           "VERDICT_REFLECT", "VERDICT_ABORT", "HEDGE_PATTERNS", "VAGUE_PATTERNS"]
