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

# 理念8「限最大存储条数防磁盘打满」：route_outcomes.jsonl 单文件追加硬上限。
# 与 autopilot._REFLECTION_MEMORY_MAX=200 / trace_store._MAX_TRACE_FILES=500 同源纪律。
# 路由记录频率远高于反思记忆（每次 route() 都记一条），故上限放大到 2000；
# 达上限时删最旧 80%（保留最新 _MAX_ROUTE_OUTCOMES//5 条），与反思记忆同比例。
_MAX_ROUTE_OUTCOMES = 2000
# 每次 record 都读全文件行数开销大，用内存计数器每 N 次才检查一次。
# 进程重启计数器归零只会让首次裁剪晚到 N 次后，不影响正确性。
_TRIM_CHECK_EVERY = 100


class RouteOutcomeStore:
    """线程安全的路由结果 JSONL 落盘器。"""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._since_last_trim = 0
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
            self._since_last_trim += 1
            if self._since_last_trim >= _TRIM_CHECK_EVERY:
                self._since_last_trim = 0
                self._enforce_rotation()

    def _enforce_rotation(self) -> None:
        """理念8：route_outcomes.jsonl 行数超 _MAX_ROUTE_OUTCOMES 时删最旧 80%。

        必须在已持有 self._lock 时调用（不可重入 Lock，不再 acquire）。
        best-effort：裁剪失败只记日志，不影响主流程（与 record 落盘语义一致）。
        """
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, encoding="utf-8") as f:
                lines = [ln for ln in f if ln.strip()]
            if len(lines) >= _MAX_ROUTE_OUTCOMES:
                # 保留最新 1/5（删最旧 80%），与 autopilot 反思记忆同比例
                keep = lines[_MAX_ROUTE_OUTCOMES // 5:]
                with open(self.path, "w", encoding="utf-8") as f:
                    f.writelines(keep)
        except Exception as e:  # noqa: BLE001 - 裁剪失败不致命
            import logging
            logging.getLogger(__name__).debug(
                "route_outcomes rotation failed: %s", e)

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
