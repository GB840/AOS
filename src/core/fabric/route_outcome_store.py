"""RouteOutcomeStore — 路由结果的结构化 Trace 落盘。

AOS 第 8 条理念：黑盒不可训，白盒才可进化。
route() 每次尝试（能力 → 引擎 → 档位）的成功 / 失败 / 耗时，是路由维度最真实、
最可学习的信号。此前 route() 跑完不记录、Trace 也只在内存——本模块把它落盘为
JSONL，供 RoutePredictor 从中学习「哪些 (能力,引擎,档位) 组合更可能成功」。

铁律：绝不编造。只记录真实发生的调用结果；没有调用就没有记录。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

# 落盘到项目根的 _traces/ 目录（与 autopilot 的 reflection_memory.jsonl 同处，
# 统一作为 AOS 的「白盒进化」数据池）。
_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "_traces",
    "route_outcomes.jsonl",
)

# 训练所需的最小样本数：低于此数 predictor 不训练、诚实回落静态策略。
_MIN_SAMPLES = 8


class RouteOutcomeStore:
    """线程安全的路由结果 JSONL 落盘器。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)

    def record(
        self,
        capability: str,
        engine: str,
        tier: str,
        ok: bool,
        latency_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """记录一次路由尝试的真实结果。"""
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "capability": capability,
            "engine": engine,
            "tier": tier or "",
            "ok": bool(ok),
            "latency_ms": float(latency_ms),
            "error": error,
        }
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def load(self) -> List[Dict[str, Any]]:
        """读回全部记录（损坏行跳过，不中断）。"""
        if not os.path.exists(self.path):
            return []
        out: List[Dict[str, Any]] = []
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except Exception:
                        continue
        return out

    def count(self) -> int:
        """不加载全量、直接数行，避免大文件开销。"""
        if not os.path.exists(self.path):
            return 0
        with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)

    def trainable(self, min_samples: int = _MIN_SAMPLES) -> bool:
        """是否积累够训练样本。"""
        return self.count() >= min_samples
