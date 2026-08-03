"""白盒进化蒸馏引擎（任务272 / 白皮书 3.3）。

从全链路执行 Trace（结构化 JSON，理念8）蒸馏『不可靠引擎』经验，
产出可回读 Registry / FabricHub 路由决策的沉底建议。

白盒：进化来自可复核证据（每引擎成功率统计），而非盲目改运行时代码
（对比 HyperAgents 直接改自己源码）。安全、可解释、可回退。

设计：
  - ingest(trace)：累加每 (capability, engine) 的成功/失败统计。
  - distill()：识别不可靠引擎（样本充足且失败率超阈值）→ 沉底建议。
  - 持久化：可选落盘 JSONL，进程重启后经验不丢（有界、可复核）。
"""
import os
import time
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

from .value_ledger import ValueLedger  # 原则6 价值回流：蒸馏出的经验记入用户账本

logger = logging.getLogger(__name__)

# 沉底阈值：引擎在 >= MIN_SAMPLES 次出现且失败率 >= SINK_FAIL_RATE 时建议沉底
MIN_SAMPLES = 5
SINK_FAIL_RATE = 0.5
# 运行时从路由 outcome 喂样本时的落盘节流间隔（秒），避免热路径每条都写盘。
SAVE_INTERVAL_SEC = 30


@dataclass
class EngineStat:
    engine: str
    capability: str
    total: int = 0
    ok: int = 0
    fail: int = 0
    last_error: str = ""

    @property
    def fail_rate(self) -> float:
        return (self.fail / self.total) if self.total else 0.0

    @property
    def reliable(self) -> bool:
        return self.total >= MIN_SAMPLES and self.fail_rate < SINK_FAIL_RATE


class EvolutionDistiller:
    """从执行 Trace 蒸馏引擎可靠性经验，产出沉底建议（白盒进化）。"""

    def __init__(self, store_path: Optional[str] = None,
                 value_ledger: Optional["ValueLedger"] = None):
        self.store_path = store_path
        self._value_ledger = value_ledger
        self.stats: Dict[str, EngineStat] = {}
        self._last_save = 0.0
        self._load()

    def _key(self, capability: str, engine: str) -> str:
        return f"{capability}::{engine}"

    def ingest(self, trace: Dict[str, Any]) -> None:
        """从一个执行 Trace 累加每引擎统计。

        trace 结构: {"steps":[{"capability":..., "engine":..., "ok":bool, "error":str}]}
        """
        for step in trace.get("steps", []):
            cap = step.get("capability", "?")
            eng = step.get("engine", "unknown")
            ok = bool(step.get("ok"))
            key = self._key(cap, eng)
            st = self.stats.get(key) or EngineStat(engine=eng, capability=cap)
            st.total += 1
            if ok:
                st.ok += 1
            else:
                st.fail += 1
                st.last_error = (step.get("error") or "")[:200]
            self.stats[key] = st
        self._save()

    def record_outcome(self, capability: str, engine: str, ok: bool,
                       error: str = "") -> None:
        """运行时从路由 outcome 增量喂样本（节流落盘，热路径安全）。

        与 ingest() 等价地累加单引擎统计，但落盘经 _maybe_save 节流，
        避免 route() 每条请求都重写整份 JSONL。
        """
        key = self._key(capability, engine)
        st = self.stats.get(key) or EngineStat(engine=engine, capability=capability)
        st.total += 1
        if ok:
            st.ok += 1
        else:
            st.fail += 1
            st.last_error = (error or "")[:200]
        self.stats[key] = st
        self._maybe_save()

    def distill(self) -> List[Dict[str, Any]]:
        """蒸馏出沉底建议：不可靠引擎（高失败率 + 样本充足）。"""
        out: List[Dict[str, Any]] = []
        for key, st in self.stats.items():
            if st.total >= MIN_SAMPLES and st.fail_rate >= SINK_FAIL_RATE:
                rec = {
                    "action": "sink",
                    "capability": st.capability,
                    "engine": st.engine,
                    "samples": st.total,
                    "fail_rate": round(st.fail_rate, 3),
                    "reason": f"{st.fail}/{st.total} 失败，超沉底阈值 {SINK_FAIL_RATE}",
                    "last_error": st.last_error,
                }
                out.append(rec)
        # 原则6 价值回流：用户 trace 蒸馏出的经验，记进用户自己的价值账本。
        # 这是「劳动有报」的真实承接——用户的劳动产物归用户所有、可带走。
        if self._value_ledger is not None:
            for rec in out:
                self._value_ledger.record(
                    "lesson",
                    f"{rec['capability']}::{rec['engine']}",
                    rec.get("reason", ""),
                )
        return out

    def reliable_engines(self) -> List[str]:
        return [k for k, st in self.stats.items() if st.reliable]

    def _load(self) -> None:
        if not self.store_path or not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    d = json.loads(line)
                    st = EngineStat(
                        engine=d.get("engine", "unknown"),
                        capability=d.get("capability", "?"),
                        total=d.get("total", 0),
                        ok=d.get("ok", 0),
                        fail=d.get("fail", 0),
                        last_error=d.get("last_error", ""),
                    )
                    self.stats[self._key(st.capability, st.engine)] = st
        except Exception as e:  # noqa: BLE001
            logger.warning("加载蒸馏记忆失败: %s", e)

    def _save(self) -> None:
        """立即落盘（ingest 调用；同时刷新节流时间戳）。"""
        self._last_save = time.time()
        self._write()

    def _write(self) -> None:
        if not self.store_path:
            return
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                for st in self.stats.values():
                    f.write(json.dumps(asdict(st), ensure_ascii=False) + "\n")
        except Exception as e:  # noqa: BLE001
            logger.warning("保存蒸馏记忆失败: %s", e)

    def _maybe_save(self) -> None:
        """运行时喂样本节流落盘：距上次写盘 < SAVE_INTERVAL_SEC 则跳过。"""
        if not self.store_path:
            return
        now = time.time()
        if self._last_save and (now - self._last_save) < SAVE_INTERVAL_SEC:
            return
        self._save()
