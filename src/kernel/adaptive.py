"""内核自适应中枢 —— 把离散的「稳态(homeostasis)」与「失败学习(learning_loop)」
两个理念模块真正接活成一个可运行的反馈闭环。

设计目标（对齐用户批评「器基本的自适应都没有弄」）：
- 不重造轮子：直接复用 Homeostasis（负反馈稳态）与 FailureMemory/analyze_failure
  （失败学习），二者原本是零引用的孤立死代码，本中枢是它们真正的接线点。
- 真接活：observe() 接收任务成败 → 映射为体征读数 + 写入失败记忆；
  corrections() 汇总稳态纠偏；apply_corrections() 真实执行纠偏动作（作用在
  LiveEvolutionEngine 上）；fix_hints() 返回下次可直接用的已知修复。
- 可注入：memory_path 可注入临时目录，离线真跑不污染生产记忆库、不连外网。

诚实分级：本模块是②级（代码 + 单元测试实证），不宣称③级端到端
（③需真 LLM + 主机环境，详见 docs/CONSTITUTION_ALIGNMENT_AUDIT_2026-08-04.md）。

对齐（每一处改动都可回溯到全局，非零敲碎打）：
- 白皮书 L2E 体感稳态系统：体征必须是**真实内在状态**，不能是一个数的多种变形；
- 九大理念 2/2.5/8/9：失败即训练、长程自主反思、白盒才可进化、自动进化；
- 四层架构第①层「多租户隔离底座」+ 母纲「主权归你永不收割」：
  自适应中枢按租户隔离持有，A 租户的失败教训绝不串到 B 租户。
"""

from __future__ import annotations

import logging
import os
import re
import statistics
import tempfile
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from kernel.homeostasis import Homeostasis, Vital, DEFAULT_ACTIONS
from kernel.learning_loop import FailureMemory, analyze_failure

logger = logging.getLogger(__name__)


def _clamp01(x: float) -> float:
    """把任意读数夹到 [0,1]（体征的物理界）。"""
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else float(x))


class AdaptiveCore:
    """内核自适应中枢：稳态 + 失败学习的统一观测与纠偏。

    典型用法：
        core = AdaptiveCore(memory_path=tmp_dir)   # 离线注入临时路径，真跑不污染生产
        core.observe(success=False, task="...", error="TimeoutError: ...", capability="web.search")
        for corr in core.corrections():             # 稳态纠偏（失败发生即非空）
            core.apply_corrections(engine, [corr])  # 真实作用到 live 引擎参数
        hints = core.fix_hints(task)                # 下次任务前取出已知修复
    """

    def __init__(self,
                 memory_path: Optional[str] = None,
                 instability_threshold: int = 3,
                 history_window: int = 50,
                 concurrency_base: int = 3,
                 concurrency_floor: int = 1,
                 tenant_id: Optional[str] = None):
        # 稳态控制器：持 AOS 默认体征组（energy/focus/mood/debt/error_rate）
        self.homeostasis = Homeostasis.with_defaults()
        self.homeostasis.instability_threshold = max(1, int(instability_threshold))
        # 补注册 latency_ms 体征：DEFAULT_ACTIONS 里本就有 switch_engine_tier:light
        # 的映射，但 with_defaults() 漏注册 → 之前透传的真实延迟永远被 tick 跳过
        # （这是真实存在的断线，不是新功能）。读数已归一化：1.0 == 2000ms。
        self.homeostasis.register(Vital("latency_ms", setpoint=0.5, deadband=0.1,
                                        higher_is_better=False))
        # 租户身份（四层架构第①层：多租户隔离底座；None = 自用模式）
        self.tenant_id = tenant_id
        # 失败记忆库：可注入临时路径，离线真跑不写生产库
        self.memory = FailureMemory(memory_path)
        self._history_window = history_window
        # 体征滚动窗口（最近 N 次读数）
        self._readings: List[Dict[str, float]] = []
        # 计数（累计；仅在真实指标缺失时作降级折算用）
        self._tasks_seen: int = 0
        self._tasks_failed: int = 0
        # ---- 真实 runtime 观测窗口（体征的真实来源，取代旧版「一个数五种折算」）----
        self._outcome_window: List[bool] = []     # 最近 N 次真实成败
        self._latency_window: List[float] = []    # 最近 N 次真实延迟(ms)
        self._tokens_total: float = 0.0           # 真实累计 token 消耗
        self._tokens_wasted: float = 0.0          # 失败任务白烧掉的真实 token
        self._token_budget: float = 0.0           # 真实 token 预算（如上层给了）
        self._last_runtime: Dict[str, float] = {}  # 最近一次真实指标原样留存（审计）
        self._reading_sources: Dict[str, str] = {}  # 每个体征来源：runtime*/derived
        # ---- 真实并发旋钮（reduce_concurrency 的真实作用对象）----
        self._concurrency_base = max(1, int(concurrency_base))
        self._concurrency_floor = max(1, int(concurrency_floor))
        self._concurrency_limit: Optional[int] = None   # None = 不干预，用调用方默认
        self._stable_streak: int = 0                    # 连续稳定次数（用于回升并发）
        # 最近一次稳态纠偏结果
        self._last_corrections: List[Any] = []
        # 是否有过任意不稳定（供测试断言：稳态确实检测到了）
        self.ever_unstable: bool = False
        # 已执行的纠偏动作（审计轨迹）
        self._applied_actions: List[str] = []
        # 环节级状态（环节隔离 + 高重度 用）：每环节观测/失败计数
        self._stage_seen: Dict[str, int] = {}
        self._stage_failed: Dict[str, int] = {}
        self._stage_ticks: int = 0   # 环节观测总次数（与任务级口径分开，不串味）

    # ---------------------------------------------------------- 观测
    def observe(self,
                success: bool,
                task: str = "",
                error: str = "",
                capability: str = "",
                latency_ms: float = 0.0,
                runtime_metrics: Optional[Dict[str, float]] = None) -> None:
        """一次任务结果 → 更新体征读数（真稳态评估）+ 写入失败记忆（真学习）。

        Args:
            runtime_metrics: **真实运行时指标**（体征的第一来源），可含
                latency_ms / tokens / token_budget / error_rate / concurrency。
                缺哪个就只有那个体征降级为成败折算，其余仍取真值。
        """
        self._tasks_seen += 1
        rm: Dict[str, float] = dict(runtime_metrics or {})
        if latency_ms > 0 and "latency_ms" not in rm:
            rm["latency_ms"] = float(latency_ms)

        # 先记账、先写记忆，再取体征 —— 修正旧版 off-by-one：
        # 旧版在 _derive_readings 之后才 _tasks_failed += 1 / memory.add，
        # 导致「本次失败」根本没进入本次体征，稳态永远慢一拍。
        if not success:
            self._tasks_failed += 1
            if capability or error:
                try:
                    rec = analyze_failure(
                        capability or "action.code_exec",
                        error or "task failed",
                        task,
                    )
                    self.memory.add(rec)
                except Exception:
                    # 记忆写入失败绝不破坏主流程
                    logger.warning("AdaptiveCore.observe: 失败记忆写入异常，已跳过", exc_info=True)

        readings = self._derive_readings(success, rm)

        # 滚动窗口
        self._readings.append(readings)
        if len(self._readings) > self._history_window:
            self._readings.pop(0)

        # 真实稳态评估（带死区比例控制 + 失稳计数），存入 last_corrections
        self._last_corrections = self.homeostasis.tick(readings)
        if self._last_corrections:
            self.ever_unstable = True
            self._stable_streak = 0
        else:
            # 动态：连续稳定则把此前压下去的并发逐步还回去（不是单向阀）
            self._stable_streak += 1
            if self._stable_streak >= 3 and self._concurrency_limit is not None:
                self.restore_concurrency()
                self._stable_streak = 0

    # ---------------------------------------------------------- 体征推导
    def _derive_readings(self,
                         success: bool,
                         rm: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        """把**真实 runtime 指标**映射成体征读数；缺失指标才退回成败折算。

        与旧版的本质区别：旧版五个体征全是同一个 err_rate 的线性变形（等于稳态
        只看得见一个数）；现在每个体征各有**独立的真实来源**：

          error_rate ← 真实错误率（外部注入 or 最近 N 次真实成败滑窗）
          latency_ms ← 真实延迟滑窗中位数（归一化，1.0 == 2000ms）
          energy     ← 真实 token 预算余量；无预算则用真实「白烧 token 占比」
          focus      ← 真实延迟抖动（变异系数 CV，越抖越涣散）
          mood       ← 真实近况成功率（滑窗，不是累计）
          debt       ← 真实未解决失败模式数（记忆库 unresolved = 真技术债）

        每个体征来源记录进 self._reading_sources（runtime* / derived），
        可被测试与审计直接断言「体征确实取自真实运行时」。
        """
        rm = dict(rm or {})
        self._last_runtime = dict(rm)
        src: Dict[str, str] = {}

        # ---- 真实观测窗口滚动 ----
        self._outcome_window.append(bool(success))
        if len(self._outcome_window) > self._history_window:
            self._outcome_window.pop(0)

        lat = float(rm.get("latency_ms", 0.0) or 0.0)
        if lat > 0:
            self._latency_window.append(lat)
            if len(self._latency_window) > self._history_window:
                self._latency_window.pop(0)

        tok = float(rm.get("tokens", 0.0) or 0.0)
        if tok > 0:
            self._tokens_total += tok
            if not success:
                self._tokens_wasted += tok
        budget = float(rm.get("token_budget", 0.0) or 0.0)
        if budget > 0:
            self._token_budget = budget

        cum_err = (self._tasks_failed / self._tasks_seen) if self._tasks_seen else 0.0
        win = self._outcome_window
        win_success = (sum(1 for o in win if o) / len(win)) if win else (1.0 - cum_err)

        r: Dict[str, float] = {}

        # error_rate ← 真实错误率
        if "error_rate" in rm:
            r["error_rate"] = _clamp01(float(rm["error_rate"]))
            src["error_rate"] = "runtime"
        elif win:
            r["error_rate"] = _clamp01(1.0 - win_success)
            src["error_rate"] = "runtime_window"
        else:
            r["error_rate"] = _clamp01(cum_err)
            src["error_rate"] = "derived"

        # latency_ms ← 真实延迟中位数（无真实延迟就不产生该读数，稳态自动跳过）
        if self._latency_window:
            r["latency_ms"] = _clamp01(statistics.median(self._latency_window) / 2000.0)
            src["latency_ms"] = "runtime"

        # energy ← 真实资源余量（预算优先，其次真实白烧占比）
        if self._token_budget > 0:
            r["energy"] = _clamp01(1.0 - self._tokens_total / self._token_budget)
            src["energy"] = "runtime_budget"
        elif self._tokens_total > 0:
            r["energy"] = _clamp01(1.0 - self._tokens_wasted / self._tokens_total)
            src["energy"] = "runtime_waste"
        else:
            r["energy"] = max(0.0, 0.5 - 0.3 * cum_err)
            src["energy"] = "derived"

        # focus ← 真实延迟抖动（CV=0 极专注；CV≥1 完全涣散）
        if len(self._latency_window) >= 3:
            mean_l = statistics.fmean(self._latency_window)
            cv = (statistics.pstdev(self._latency_window) / mean_l) if mean_l > 0 else 0.0
            r["focus"] = _clamp01(1.0 - min(1.0, cv))
            src["focus"] = "runtime_jitter"
        else:
            r["focus"] = 0.5 if success else 0.25
            src["focus"] = "derived"

        # mood ← 真实近况成功率
        r["mood"] = _clamp01(win_success)
        src["mood"] = "runtime_window" if win else "derived"

        # debt ← 真实未解决失败模式数（技术债的真实存量，非「失败次数×0.5」）
        r["debt"] = float(min(5.0, self.memory_stats["unresolved"]))
        src["debt"] = "runtime_memory"

        self._reading_sources = src
        return r

    def vital_sources(self) -> Dict[str, str]:
        """每个体征的真实来源（runtime* = 取自真实运行时；derived = 降级折算）。"""
        return dict(self._reading_sources)

    def last_runtime_metrics(self) -> Dict[str, float]:
        """最近一次注入的真实运行时指标原样留存（审计用）。"""
        return dict(self._last_runtime)

    # ---------------------------------------------------------- 环节级观测
    def observe_stage(self, stage: str, ok: bool, error: str = "",
                      latency_ms: float = 0.0) -> None:
        """环节级观测：把单个环节（规划/执行/评估/反思/进化…）的成败折算进
        全局稳态 + 写入共享失败记忆库。

        设计：不另建稳态实例（避免状态分裂），而是复用同一套体征读数逻辑，
        使「单环节高频死亡」会推高 error_rate → 触发稳态纠偏（高重度生效）。
        同时按 `stage.{name}` 维度记失败记忆，便于后续按环节聚合根因。

        口径订正：环节观测**不再**混进 tasks_seen/tasks_failed（那是任务级口径），
        改记 _stage_ticks。否则「跑了 8 个任务」会因为中间触发一次 evolve 环节
        被报成 9，属统计串味。环节成败仍进真实成败滑窗，稳态照常被驱动。
        """
        self._stage_seen[stage] = self._stage_seen.get(stage, 0) + 1
        self._stage_ticks += 1
        if not ok:
            self._stage_failed[stage] = self._stage_failed.get(stage, 0) + 1
            # 环节失败也写失败记忆（与任务级 observe 同源共享库）
            # 先写后取体征：debt 体征取自记忆库 unresolved，必须先落库才不慢一拍
            if error:
                try:
                    rec = analyze_failure(f"stage.{stage}", error, f"stage:{stage}")
                    self.memory.add(rec)
                except Exception:
                    logger.warning("AdaptiveCore.observe_stage: 记忆写入异常，已跳过", exc_info=True)
        readings = self._derive_readings(ok, {"latency_ms": float(latency_ms or 0.0)})
        self._readings.append(readings)
        if len(self._readings) > self._history_window:
            self._readings.pop(0)
        self._last_corrections = self.homeostasis.tick(readings)
        if self._last_corrections:
            self.ever_unstable = True
            self._stable_streak = 0
        else:
            self._stable_streak += 1
            if self._stable_streak >= 3 and self._concurrency_limit is not None:
                self.restore_concurrency()
                self._stable_streak = 0

    def record_stage_failure(self, stage: str, error: str) -> None:
        """显式把某环节的死亡写入共享失败记忆库（供 StageGuard 重试耗尽后调用）。"""
        try:
            rec = analyze_failure(f"stage.{stage}", error, f"stage:{stage}")
            self.memory.add(rec)
        except Exception:
            logger.warning("AdaptiveCore.record_stage_failure: 写入异常，已跳过", exc_info=True)

    def record_failure(self, task: str, capability: str, error: str) -> None:
        """把一次任务级失败（指定步骤+错误）写入共享失败记忆库。

        与 observe()/StageGuard 同源、同实例 —— 这是自进化闭环「写→读」能闭环的
        关键：autopilot.run() 主路径通过它写，下一轮 PREFLIGHT 通过 fix_hints() 读，
        二者指向 self.memory 同一个对象，同一进程内立即可见（无需重载磁盘）。
        """
        try:
            rec = analyze_failure(
                capability or "action.code_exec",
                error or "task failed",
                task,
            )
            self.memory.add(rec)
        except Exception:
            logger.warning("AdaptiveCore.record_failure: 写入异常，已跳过", exc_info=True)

    def stage_health(self) -> Dict[str, Any]:
        """每环节失败率（供「高重度」环节判断是否需要升级处置 / 上层观测）。"""
        out: Dict[str, Any] = {}
        for stage, seen in self._stage_seen.items():
            failed = self._stage_failed.get(stage, 0)
            out[stage] = {
                "seen": seen,
                "failed": failed,
                "fail_rate": (failed / seen) if seen else 0.0,
            }
        return out

    # ---------------------------------------------------------- 汇总纠偏
    def corrections(self) -> List[Any]:
        """返回最近一次稳态评估产出的纠偏动作（失败发生即非空）。"""
        return self._last_corrections

    def fix_hints(self, task: str = "", capability: str = "") -> List[str]:
        """返回已知修复提示（来自失败记忆库，下次任务前可直接注入）。

        - 指定 capability + task：按任务相似度查该步骤的已知修复（PREFLIGHT 命中）
        - 指定 capability 无 task：直接按步骤匹配（跳过相似度，便于按步骤取修复）
        - 都不指定：返回全局最近未解决根因的修复提示
        """
        if capability:
            if task:
                return self.memory.get_fix_hints(task, capability)
            return [ (r.resolution or r.fix_hint)
                     for r in self.memory._records.values()
                     if r.failed_step == capability and (r.resolution or r.fix_hint) ]
        hints: List[str] = []
        for rec in self.memory._records.values():
            if rec.fix_hint and not rec.resolved:
                hints.append(rec.fix_hint)
        return hints[:5]

    # ---------------------------------------------------------- 真实并发旋钮
    def concurrency_limit(self) -> Optional[int]:
        """当前自适应并发上限（None = 未干预，由调用方自己的默认值决定）。

        这是 reduce_concurrency 的**真实作用对象**：autopilot 的 `_max_parallel()`
        与 LiveEvolutionEngine 的活跃 agent 工作集都会读它，稳态一压真的少并发。
        """
        return self._concurrency_limit

    def reduce_concurrency(self, effort: float = 0.5) -> int:
        """真降并发上限（力度越大降得越多，最低不低于 concurrency_floor）。"""
        cur = self._concurrency_limit if self._concurrency_limit is not None \
            else self._concurrency_base
        eff = 0.0 if effort < 0 else (1.0 if effort > 1 else float(effort))
        step = max(1, int(round(cur * 0.5 * eff))) if eff > 0 else 1
        self._concurrency_limit = max(self._concurrency_floor, cur - step)
        return self._concurrency_limit

    def restore_concurrency(self, step: int = 1) -> Optional[int]:
        """稳态恢复后逐步回升并发（动态：降得下去也回得来，不是单向阀）。"""
        if self._concurrency_limit is None:
            return None
        new = self._concurrency_limit + max(1, int(step))
        # 回到基线即撤销干预（还权给调用方默认值）
        self._concurrency_limit = None if new >= self._concurrency_base else new
        return self._concurrency_limit

    def effective_concurrency(self, default: int) -> int:
        """给调用方用的收口函数：默认值与自适应上限取小。"""
        lim = self._concurrency_limit
        return max(1, int(default) if lim is None else min(int(default), lim))

    # ---------------------------------------------------------- 真实执行纠偏
    def apply_corrections(self,
                          engine: Any = None,
                          corrections: Optional[List[Any]] = None) -> List[str]:
        """把稳态纠偏动作真实执行掉（engine 可为 None，此时只作用于中枢自身旋钮）。

        动作映射（DEFAULT_ACTIONS 已定义，这里给出真实执行）：
          reduce_concurrency     → **真降并发上限**（中枢旋钮 + 引擎 _max_concurrency）
          rest_cycle            → 拉大 evolution_interval（休眠=降低进化频率）
          switch_engine_tier:light → 缩小 max_population（轻量档）
          pay_debt_first        → 停掉 fitness 最差的底部 agent（清账）
          其余动作               → 仅记录，留给上层 rhythm 调度，不误伤内核

        订正记录：旧版把 reduce_concurrency 映射到 evolution_interval —— 那是
        「进化频率」不是「并发」，属真实错配（动作名与效果不符）。现已改为作用在
        真实并发旋钮上，rest_cycle 才保留 evolution_interval（休眠语义正确）。
        """
        applied: List[str] = []
        for c in (corrections if corrections is not None else self._last_corrections):
            action = getattr(c, "action", "")
            effort = getattr(c, "effort", 0.0)
            try:
                if action == "reduce_concurrency":
                    new_limit = self.reduce_concurrency(effort)
                    applied.append(f"{action}:concurrency->{new_limit}")
                    if engine is not None and hasattr(engine, "_max_concurrency"):
                        engine._max_concurrency = max(
                            1, min(int(engine._max_concurrency), new_limit))
                        applied.append(
                            f"{action}:engine_max_concurrency->{engine._max_concurrency}")
                elif action == "rest_cycle":
                    if engine is None or not hasattr(engine, "_evolution_interval"):
                        applied.append(f"logged:{action}")
                        continue
                    engine._evolution_interval = max(
                        1, int(engine._evolution_interval * (1 + effort)))
                    applied.append(f"{action}:evolution_interval->{engine._evolution_interval}")
                elif engine is None:
                    applied.append(f"logged:{action}")
                elif action == "switch_engine_tier:light":
                    engine._max_population = max(
                        engine._min_population,
                        int(engine._max_population * (1 - 0.3 * effort)))
                    applied.append(f"{action}:max_population->{engine._max_population}")
                elif action == "pay_debt_first":
                    bottom = engine.fitness.bottom_agents(1)
                    if bottom:
                        engine.kernel.stop_agent(bottom[0].agent_id)
                        applied.append(f"{action}:stop->{bottom[0].agent_id}")
                else:
                    # 暂不强改内核参数，仅记录（如 reset_focus/seek_easy_win 等）
                    applied.append(f"logged:{action}")
            except Exception:
                logger.warning("AdaptiveCore.apply_corrections: 动作 %s 执行失败，跳过", action, exc_info=True)
        self._applied_actions.extend(applied)
        return applied

    # ---------------------------------------------------------- 快照
    def snapshot(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "tasks_seen": self._tasks_seen,
            "tasks_failed": self._tasks_failed,
            "stage_ticks": self._stage_ticks,
            "stage_health": self.stage_health(),
            "failure_patterns": self.memory_stats,
            "homeostasis_stable": self.homeostasis.is_stable(),
            "unstable_vitals": self.homeostasis.unstable_vitals(),
            "should_hibernate": self.homeostasis.should_hibernate(),
            "ever_unstable": self.ever_unstable,
            "applied_actions": self._applied_actions,
            # 真实运行时可观测面（体征来源 + 真实指标 + 并发旋钮现值）
            "vital_sources": dict(self._reading_sources),
            "last_runtime_metrics": dict(self._last_runtime),
            "last_readings": dict(self._readings[-1]) if self._readings else {},
            "concurrency_limit": self._concurrency_limit,
            "concurrency_base": self._concurrency_base,
            "tokens_total": round(self._tokens_total, 2),
            "tokens_wasted": round(self._tokens_wasted, 2),
        }

    @property
    def memory_stats(self) -> Dict[str, Any]:
        recs = self.memory._records
        total = len(recs)
        resolved = sum(1 for r in recs.values() if r.resolved)
        return {
            "total_patterns": total,
            "resolved": resolved,
            "unresolved": total - resolved,
        }

    @property
    def tasks_seen(self) -> int:
        """累计观测到的任务数（只读）。"""
        return self._tasks_seen

    @property
    def tasks_failed(self) -> int:
        """累计观测到的失败任务数（只读）。"""
        return self._tasks_failed


class StageGuard:
    """环节级隔离 + 重度分级 + 动态恢复。

    把「芯粒隔离≠多Agent」「失败即训练(有生有灭)」两条理念直接落到控制环的
    **每一个环节**（规划/执行/评估/反思/进化），回应「一次死了后面都挨这死」：

    - 隔离（芯粒 crash boundary）：环节内异常被本地捕获，绝不级联杀整轮；
    - 高重度（severity="high"）：控制环关键链路死亡记 severity=high、写入共享失败
      记忆、触发稳态纠偏；重试耗尽后**不静默吞**，返回结构化 (ok=False, None, err)，
      让调用方以失败优雅收尾（仍跑后续环节、仍写记忆、仍落盘）；
    - 动态（severity="dynamic"）：单点死亡时调用 fallback 拿降级产出（或跳过带教训），
      整轮在单点死亡后**继续**跑后续环节，体现「动态」自适应。

    用法：
        g = StageGuard(core, "execute")
        ok, val, err = g.run(lambda: _execute(...), severity="high")
        if not ok:
            # 高重度：结构化收尾，不崩
        ok2, r, err2 = StageGuard(core, "reflect").run(
            lambda: _reflect(...), severity="dynamic", fallback=lambda e: None)
        # 动态：reflect 死了也用 fallback 继续
    """

    def __init__(self, core: "AdaptiveCore", stage: str) -> None:
        self.core = core
        self.stage = stage

    def run(self,
            fn: Callable[[], "T"],
            *,
            severity: str = "high",
            fallback: Optional[Callable[[Optional[Exception]], Any]] = None,
            max_retry: int = 1) -> Tuple[bool, Any, Optional[Exception]]:
        """执行环节 fn；失败则隔离 + 记记忆 + 按需重试/降级。

        Returns:
            (ok, value, error)
            - ok=True：环节成功，value 为其返回值；
            - ok=False：重试耗尽；value=fallback 产出（severity=dynamic 且给了 fallback）
              或 None（severity=high 或未给 fallback）；error=最后一个异常。
        """
        last_err: Optional[Exception] = None
        for attempt in range(max_retry + 1):
            try:
                val = fn()
                self.core.observe_stage(self.stage, ok=True)
                return True, val, None
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning("StageGuard[%s] 第%d次尝试失败: %s", self.stage, attempt + 1, e)
                self.core.observe_stage(self.stage, ok=False, error=str(e))
        # 重试耗尽 → 记失败记忆（共享库，同源）
        self.core.record_stage_failure(self.stage, str(last_err))
        # 动态恢复：给 fallback 就用降级产出，整轮继续
        if severity == "dynamic" and fallback is not None:
            try:
                fb = fallback(last_err)
                logger.info("StageGuard[%s] 降级恢复(动态): 使用 fallback 产出", self.stage)
                return False, fb, last_err
            except Exception as e2:  # noqa: BLE001
                logger.warning("StageGuard[%s] fallback 也失败: %s", self.stage, e2)
                return False, None, e2
        # 高重度：不静默吞，返回结构化失败（调用方优雅收尾，不崩）
        return False, None, last_err


# ---- 按租户隔离的中枢注册表（四层架构第①层：多租户隔离底座）----
#
# 旧版是进程级全局单例 —— 在单创OS 多租户模式下，A 租户的失败教训会被 B 租户
# 的 PREFLIGHT 读回并注入其规划输入，这是**跨租户数据串味**，直接违反母纲
# 「主权归你，永不收割」。现改为按 tenant_id 维度持有，各租户各自一套稳态与
# 失败记忆库；tenant_id=None 时退化为共享默认实例，自用模式行为零变化。
_DEFAULT_TENANT = "__default__"
_cores: Dict[str, "AdaptiveCore"] = {}
_core_lock = threading.Lock()


def _tenant_key(tenant_id: Optional[str]) -> str:
    key = (tenant_id or "").strip()
    return key or _DEFAULT_TENANT


def _tenant_memory_path(key: str) -> Optional[str]:
    """租户专属失败记忆库路径；默认租户返回 None（沿用 FailureMemory 原默认路径）。"""
    if key == _DEFAULT_TENANT:
        return None
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:64] or "tenant"
    base = os.path.join(os.path.dirname(__file__), "..", "..",
                        "_learning_memory", "tenants", safe)
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        base = os.path.join(tempfile.gettempdir(), "aos_learning_memory", safe)
        os.makedirs(base, exist_ok=True)
    return os.path.join(base, "failure_memory.json")


def get_adaptive_core(memory_path: Optional[str] = None,
                      tenant_id: Optional[str] = None) -> "AdaptiveCore":
    """返回**该租户**的内核自适应中枢（autopilot 等顶层循环用它）。

    - tenant_id=None：共享默认实例，失败记忆库与 LiveEvolutionEngine.adaptive
      同文件共享（自用模式，与旧行为完全一致）；
    - tenant_id 非空：该租户独占一套稳态 + 独占记忆库文件，互不串味。
    """
    key = _tenant_key(tenant_id)
    core = _cores.get(key)
    if core is None:
        with _core_lock:
            core = _cores.get(key)
            if core is None:
                path = memory_path or _tenant_memory_path(key)
                core = AdaptiveCore(
                    memory_path=path,
                    tenant_id=None if key == _DEFAULT_TENANT else key,
                )
                _cores[key] = core
    return core


def set_adaptive_core(core: Optional["AdaptiveCore"],
                      tenant_id: Optional[str] = None) -> None:
    """替换/清空某租户的中枢（离线测试隔离用；传 None 即移除，下次惰性重建）。"""
    key = _tenant_key(tenant_id)
    with _core_lock:
        if core is None:
            _cores.pop(key, None)
        else:
            _cores[key] = core


def reset_adaptive_cores() -> None:
    """清空全部租户中枢（测试收尾用，避免跨用例串状态）。"""
    with _core_lock:
        _cores.clear()


def list_adaptive_tenants() -> List[str]:
    """当前已实例化中枢的租户键（含默认租户），供运维观测。"""
    return sorted(_cores.keys())


__all__ = ["AdaptiveCore", "StageGuard", "get_adaptive_core", "set_adaptive_core",
           "reset_adaptive_cores", "list_adaptive_tenants"]
