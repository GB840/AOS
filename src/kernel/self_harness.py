"""Self-Harness —— AOS 自测闭环（理念9「可验证即真理」的运行时落地）。

不依赖外部服务：直接构造并探活一组核心适配器，跑一轮 eval 冒烟，
校验关键存储可写，产出结构化健康报告。任何失败都如实记录，绝不伪造
「系统健康」。

设计边界（诚实优先）：
- 只探活「AOS 自身能直接构造的适配器」，不假装探活需要重型内核单例的
  全局 fabric（避免把「内核没启」误报成「能力挂了」）。
- 离线无 key 的适配器（如 vlm 无 VLM_API_KEY）→ healthy=False，属正常降级，
  报告里给出可执行的修复建议，而非掩盖。
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SelfTestReport:
    """一轮自测的结构化报告（可直接 JSON 序列化）。"""
    timestamp: str
    overall_status: str  # "healthy" / "degraded" / "unhealthy"
    adapters: List[Dict[str, Any]] = field(default_factory=list)
    eval_smoke: Dict[str, Any] = field(default_factory=dict)
    store_checks: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "adapters": self.adapters,
            "eval_smoke": self.eval_smoke,
            "store_checks": self.store_checks,
            "recommendations": self.recommendations,
        }


class SelfHarness:
    """自测闭环驱动器。

    probe_specs: list of (engine_id, capability_str, adapter_class)。
    默认探测一组核心可导入适配器（视觉/语音等），缺失则自动跳过。
    """

    def __init__(self, probe_specs: Optional[List[Tuple[str, str, Any]]] = None) -> None:
        # 显式传 [] 表示「不要探活任何适配器」，必须尊重；只有 None 才走默认。
        self._probe_specs = self._default_probe_specs() if probe_specs is None else probe_specs

    @staticmethod
    def _default_probe_specs() -> List[Tuple[str, str, Any]]:
        specs: List[Tuple[str, str, Any]] = []
        # 视觉理解（多模态平面）
        try:
            from core.fabric.adapters.vlm_adapter import VLMAdapter
            specs.append(("vlm", "vision.understand", VLMAdapter))
        except Exception as e:  # noqa: BLE001
            logger.debug("VLMAdapter 不可导入（跳过）: %s", e)
        # 语音全双工
        try:
            from core.fabric.adapters.minicpm_o_adapter import MiniCPMOAdapter
            specs.append(("minicpm_o", "voice.omni", MiniCPMOAdapter))
        except Exception:  # noqa: BLE001
            pass
        return specs

    # ── 1) 适配器探活 ──
    def probe_adapters(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for engine_id, cap, cls in self._probe_specs:
            entry = {"engine_id": engine_id, "capability": cap,
                     "healthy": False, "detail": ""}
            try:
                inst = cls() if isinstance(cls, type) else cls
                entry["healthy"] = bool(inst.health())
                if hasattr(inst, "health_detail"):
                    try:
                        entry["detail"] = inst.health_detail()
                    except Exception as e:  # noqa: BLE001
                        entry["detail"] = f"health_detail 异常: {e}"
            except Exception as e:  # noqa: BLE001
                entry["detail"] = f"构造/探活异常: {e}"
            results.append(entry)
        return results

    # ── 2) eval 冒烟（确认评测流水线端到端可用）──
    def smoke_eval(self) -> Dict[str, Any]:
        try:
            from kernel.eval.eval_harness import EvalHarness, TrajectoryScore
            harness = EvalHarness()
            score = harness.score_trajectory(
                task_id="self_smoke",
                workflow_id="self_smoke",
                steps=[
                    {"capability": "web.search", "engine": "anysearch",
                     "ok": True, "output": {"content": "搜索命中"}},
                    {"capability": "inference.llm", "engine": "litellm",
                     "ok": True, "output": {"content": "合成报告"}},
                ],
            )
            ok = isinstance(score, TrajectoryScore) and score.total > 0
            return {
                "ok": ok,
                "score": getattr(score, "total", 0),
                "note": "内联双步轨迹评分通过" if ok else "评分异常（total<=0）",
            }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e), "note": "eval 冒烟失败"}

    # ── 3) 关键存储可写性 ──
    def check_stores(self) -> List[Dict[str, Any]]:
        checks: List[Dict[str, Any]] = []
        cand = [
            ("pulse_dir", os.environ.get("AOS_PULSE_DIR")
             or "data/workspaces/fabric/pulse"),
            ("context_dir", os.environ.get("AOS_CONTEXT_DIR")
             or "data/workspaces/fabric/context"),
            ("eval_dir", os.environ.get("AOS_EVAL_DIR")
             or "data/workspaces/fabric/eval"),
        ]
        for name, path in cand:
            rec = {"store": name, "writable": False}
            try:
                os.makedirs(path, exist_ok=True)
                tmp = os.path.join(path, ".selftest_write")
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write("ok")
                os.remove(tmp)
                rec["writable"] = True
            except Exception as e:  # noqa: BLE001
                rec["error"] = str(e)
            checks.append(rec)
        return checks

    # ── 汇总 ──
    def run_self_test(self) -> SelfTestReport:
        adapters = self.probe_adapters()
        eval_smoke = self.smoke_eval()
        stores = self.check_stores()

        healthy_count = sum(1 for a in adapters if a["healthy"])
        total = len(adapters) or 1
        ratio = healthy_count / total
        stores_ok = all(s.get("writable") for s in stores)

        if ratio >= 0.5 and eval_smoke.get("ok") and stores_ok:
            overall = "healthy"
        elif healthy_count > 0 or (eval_smoke.get("ok") and stores_ok):
            overall = "degraded"
        else:
            overall = "unhealthy"

        recs: List[str] = []
        for a in adapters:
            if not a["healthy"]:
                recs.append(
                    f"{a['engine_id']}({a['capability']}) 不可用："
                    f"检查配置/后端（如缺失 VLM_API_KEY、ollama 未起）")
        if not eval_smoke.get("ok"):
            recs.append("Eval 冒烟未通过：评测流水线可能损坏，需排查 eval_harness")
        for s in stores:
            if not s.get("writable"):
                recs.append(f"存储 {s['store']} 不可写：检查磁盘/权限（{s.get('error', '')}）")

        return SelfTestReport(
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            overall_status=overall,
            adapters=adapters,
            eval_smoke=eval_smoke,
            store_checks=stores,
            recommendations=recs,
        )
