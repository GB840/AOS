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
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from kernel.homeostasis import Homeostasis, DEFAULT_ACTIONS
from kernel.learning_loop import FailureMemory, analyze_failure

logger = logging.getLogger(__name__)


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
                 history_window: int = 50):
        # 稳态控制器：持 AOS 默认体征组（energy/focus/mood/debt/error_rate）
        self.homeostasis = Homeostasis.with_defaults()
        # 失败记忆库：可注入临时路径，离线真跑不写生产库
        self.memory = FailureMemory(memory_path)
        self._history_window = history_window
        # 体征滚动窗口（最近 N 次读数）
        self._readings: List[Dict[str, float]] = []
        # 计数（用于把成败映射成 error_rate / energy / mood 等体征）
        self._tasks_seen: int = 0
        self._tasks_failed: int = 0
        # 最近一次稳态纠偏结果
        self._last_corrections: List[Any] = []
        # 是否有过任意不稳定（供测试断言：稳态确实检测到了）
        self.ever_unstable: bool = False
        # 已执行的纠偏动作（审计轨迹）
        self._applied_actions: List[str] = []
        # 环节级状态（环节隔离 + 高重度 用）：每环节观测/失败计数
        self._stage_seen: Dict[str, int] = {}
        self._stage_failed: Dict[str, int] = {}

    # ---------------------------------------------------------- 观测
    def observe(self,
                success: bool,
                task: str = "",
                error: str = "",
                capability: str = "",
                latency_ms: float = 0.0) -> None:
        """一次任务结果 → 更新体征读数（真稳态评估）+ 写入失败记忆（真学习）。"""
        self._tasks_seen += 1
        readings = self._derive_readings(success, latency_ms)

        # 滚动窗口
        self._readings.append(readings)
        if len(self._readings) > self._history_window:
            self._readings.pop(0)

        # 真实稳态评估（带死区比例控制 + 失稳计数），存入 last_corrections
        self._last_corrections = self.homeostasis.tick(readings)
        if self._last_corrections:
            self.ever_unstable = True

        # 失败学习：失败且能定位（有步骤或错误信息）→ 写入共享失败记忆库
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

    def _derive_readings(self, success: bool, latency_ms: float) -> Dict[str, float]:
        """把任务成败映射成体征读数（0..1，越接近 setpoint 越好）。

        映射是朴素但可解释的：失败率驱动 error_rate/energy/mood/debt/focus。
        后续可换成真实 runtime 指标（真实 token 成本、真实延迟），这里先接活闭环。
        """
        err_rate = (self._tasks_failed / self._tasks_seen) if self._tasks_seen else 0.0
        r: Dict[str, float] = {
            # error_rate：累计失败占比
            "error_rate": min(1.0, err_rate),
            # energy：失败多则能量低
            "energy": max(0.0, 0.5 - 0.3 * err_rate),
            # mood：成功率正向
            "mood": max(0.0, 0.35 + 0.4 * (1.0 - err_rate)),
            # focus：本轮成功保持，失败拉低
            "focus": 0.5 if success else max(0.0, 0.5 - 0.25),
            # debt：累计失败数（归一化；Homeostasis 已设 gain=0.4 higher_is_better=False）
            "debt": min(5.0, self._tasks_failed * 0.5),
        }
        # latency 透传（如有真实延迟，命中 switch_engine_tier:light）
        if latency_ms > 0:
            r["latency_ms"] = min(1.0, latency_ms / 2000.0)
        return r

    # ---------------------------------------------------------- 环节级观测
    def observe_stage(self, stage: str, ok: bool, error: str = "") -> None:
        """环节级观测：把单个环节（规划/执行/评估/反思/进化…）的成败折算进
        全局稳态 + 写入共享失败记忆库。

        设计：不另建稳态实例（避免状态分裂），而是复用同一套体征读数逻辑，
        使「单环节高频死亡」会推高 error_rate → 触发稳态纠偏（高重度生效）。
        同时按 `stage.{name}` 维度记失败记忆，便于后续按环节聚合根因。
        """
        self._stage_seen[stage] = self._stage_seen.get(stage, 0) + 1
        if not ok:
            self._stage_failed[stage] = self._stage_failed.get(stage, 0) + 1
        # 折算成一次全局任务读数，触发稳态
        self._tasks_seen += 1
        if not ok:
            self._tasks_failed += 1
        readings = self._derive_readings(ok, 0.0)
        self._readings.append(readings)
        if len(self._readings) > self._history_window:
            self._readings.pop(0)
        self._last_corrections = self.homeostasis.tick(readings)
        if self._last_corrections:
            self.ever_unstable = True
        # 环节失败也写失败记忆（与任务级 observe 同源共享库）
        if not ok and error:
            try:
                rec = analyze_failure(f"stage.{stage}", error, f"stage:{stage}")
                self.memory.add(rec)
            except Exception:
                logger.warning("AdaptiveCore.observe_stage: 记忆写入异常，已跳过", exc_info=True)

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

    # ---------------------------------------------------------- 真实执行纠偏
    def apply_corrections(self,
                          engine: Any,
                          corrections: Optional[List[Any]] = None) -> List[str]:
        """把稳态纠偏动作真实作用到 LiveEvolutionEngine 上（针对其可调参数）。

        动作映射（DEFAULT_ACTIONS 已定义，这里给出真实执行）：
          reduce_concurrency     → 拉大 evolution_interval（降低进化频率=省资源）
          rest_cycle            → 拉大进化间隔（类休眠）
          switch_engine_tier:light → 缩小 max_population（轻量档）
          pay_debt_first        → 停掉 fitness 最差的底部 agent（清账）
          其余动作               → 仅记录，留给上层 rhythm 调度，不误伤内核
        """
        applied: List[str] = []
        for c in (corrections if corrections is not None else self._last_corrections):
            action = getattr(c, "action", "")
            effort = getattr(c, "effort", 0.0)
            try:
                if action in ("reduce_concurrency", "rest_cycle"):
                    engine._evolution_interval = max(
                        1, int(engine._evolution_interval * (1 + effort)))
                    applied.append(f"{action}:evolution_interval->{engine._evolution_interval}")
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
            "tasks_seen": self._tasks_seen,
            "tasks_failed": self._tasks_failed,
            "failure_patterns": self.memory_stats,
            "homeostasis_stable": self.homeostasis.is_stable(),
            "unstable_vitals": self.homeostasis.unstable_vitals(),
            "should_hibernate": self.homeostasis.should_hibernate(),
            "ever_unstable": self.ever_unstable,
            "applied_actions": self._applied_actions,
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


# ---- 模块级单例（与 ResilienceBus / LiveEngine 同模式，供跨循环取用） ----
_core_singleton: Optional["AdaptiveCore"] = None
_core_lock = threading.Lock()


def get_adaptive_core(memory_path: Optional[str] = None) -> "AdaptiveCore":
    """返回内核自适应中枢进程单例（autopilot 等顶层循环用它，失败记忆库与
    LiveEvolutionEngine.adaptive 同文件共享）。无则惰性创建。"""
    global _core_singleton
    if _core_singleton is None:
        with _core_lock:
            if _core_singleton is None:
                _core_singleton = AdaptiveCore(memory_path=memory_path)
    return _core_singleton


def set_adaptive_core(core: Optional["AdaptiveCore"]) -> None:
    """替换/清空进程单例（离线测试隔离用；传入 None 即复位，下次调用惰性重建）。"""
    global _core_singleton
    with _core_lock:
        _core_singleton = core


__all__ = ["AdaptiveCore", "StageGuard", "get_adaptive_core", "set_adaptive_core"]
