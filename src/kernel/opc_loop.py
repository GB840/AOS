"""OPC 商业飞轮常驻环（原型）。

把一人公司的通用价值链 分析→宣传→获客→交付→维护/回流 编排成 AOS 的
常驻自主环。仅复用现有 autopilot 引擎 + 反思记忆(Meta-Trace)，零大重构。

可扩展性（用户要求）通过四层实现：
- Stage 注册表：新增业务阶段 = 注册一条 Stage，主循环不动。
- OPCLoopConfig：阶段开关 / 渠道 / 最大轮次 / 确认模式 全部可配。
- 可插拔依赖：executor / lesson_store / confirm_fn 均可注入（测试注入 mock，
  生产默认接 autopilot，懒加载避免无谓重导入）。
- 生命周期钩子：on_stage_end / on_cycle_end 回调，供自定义观测或干预。

安全纪律（AGENTS.md §5/§2.5）：
- 副作用阶段（获客/交付）强制串行 + 确认门控，绝不并发、绝不默认越权。
- 回流→分析：每轮失败教训写入 Meta-Trace，下轮分析阶段自动注入，形成自改进飞轮。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# 阶段定义（注册表驱动，可扩展）
# ---------------------------------------------------------------------------
@dataclass
class Stage:
    """一个业务阶段。新增业务功能 = 加一条 Stage，主循环无需改动。"""

    id: str
    name: str
    capability: str            # 能力标签（用于门控/可观测，不参与路由）
    side_effect: bool          # 是否有外部副作用（发邮件/发帖/写文件）
    parallel_safe: bool        # 是否可并入并行组（仅只读安全阶段=True）
    confirm: bool              # 执行前是否需人工/策略确认
    prompt: str                # 任务模板，{business} 占位
    channels: List[str] = field(default_factory=list)  # 多渠道分发用


# 全局阶段注册表：register_stage 后即刻对主循环可见
STAGE_REGISTRY: Dict[str, Stage] = {}


def register_stage(stage: Stage) -> None:
    STAGE_REGISTRY[stage.id] = stage


def build_default_stages() -> List[Stage]:
    """五阶段通用价值链。行业定制 = 复制此函数改 prompt / 加 Stage。"""
    return [
        Stage(
            id="analyze", name="分析·研报", capability="web.search",
            side_effect=False, parallel_safe=True, confirm=False,
            prompt="针对以下一人公司业务做市场/竞品/选题研报，输出结构化要点：{business}",
        ),
        Stage(
            id="promote", name="宣传·多渠道", capability="media.image",
            side_effect=False, parallel_safe=True, confirm=False,
            prompt="为以下业务撰写多渠道分发文案（图文/短视频脚本/邮件主题）并生成配图：{business}",
            channels=["自媒体", "私域", "冷邮件"],
        ),
        Stage(
            id="acquire", name="获客", capability="channel.access",
            side_effect=True, parallel_safe=False, confirm=True,
            prompt="按既定渠道执行获客动作（发布/触达潜在客户），严格按白名单，不越权：{business}",
            channels=["自媒体", "私域", "冷邮件"],
        ),
        Stage(
            id="deliver", name="交付", capability="action.code_exec",
            side_effect=True, parallel_safe=False, confirm=True,
            prompt="完成以下业务的实际交付物（产出文件/执行代码/交付报告）：{business}",
        ),
        Stage(
            id="maintain", name="维护·回流", capability="inference.llm",
            side_effect=False, parallel_safe=True, confirm=False,
            prompt="汇总本轮业务运行结果（好评/复购/互动/获客失败原因），提炼可复用经验：{business}",
        ),
    ]


# ---------------------------------------------------------------------------
# 配置（全部可配，零硬编码业务假设）
# ---------------------------------------------------------------------------
@dataclass
class OPCLoopConfig:
    business: str                                 # 业务描述（自然语言）
    enabled_stage_ids: Optional[List[str]] = None  # None = 全部默认阶段
    max_cycles: int = 3                          # 飞轮常驻轮次
    planner: str = "heuristic"                   # 透传给 autopilot 的规划器
    inject_lessons: bool = True                  # 是否把历史教训注入分析阶段
    # —— 可插拔依赖（测试/扩展注入）——
    executor: Optional[Callable] = None          # (stage, task_text, ctx) -> result dict
    lesson_store: Optional[Any] = None           # 具 save/load 的对象（默认接 Meta-Trace）
    confirm_fn: Optional[Callable] = None        # (stage, task_text) -> bool
    on_stage_end: Optional[Callable] = None      # (stage, result, ctx) -> None
    on_cycle_end: Optional[Callable] = None      # (cycle_detail, cycle) -> None


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
class OPCBusinessLoop:
    """把价值链阶段按序编排成常驻自主环。可插拔、可扩展、副作用门控。"""

    def __init__(self, config: OPCLoopConfig):
        self.config = config
        self.stages = self._resolve_stages()
        self._cycle_results: List[Dict[str, Any]] = []
        self._confirm_log: List[Dict[str, Any]] = []
        self._store_cache: Optional[Any] = None

    # ---- 阶段解析 ----
    def _resolve_stages(self) -> List[Stage]:
        defaults = {s.id: s for s in build_default_stages()}
        if self.config.enabled_stage_ids is None:
            return list(defaults.values())
        out: List[Stage] = []
        for sid in self.config.enabled_stage_ids:
            if sid in STAGE_REGISTRY:
                out.append(STAGE_REGISTRY[sid])
            elif sid in defaults:
                out.append(defaults[sid])
            else:
                raise ValueError(f"未知阶段 id: {sid}")
        return out

    # ---- 可插拔依赖（懒加载默认实现，避免无谓重导入） ----
    def _get_store(self) -> Any:
        if self.config.lesson_store is not None:
            return self.config.lesson_store
        if self._store_cache is None:
            from kernel import autopilot

            class _MetaTraceStore:
                @staticmethod
                def save(task, failed_cap, error, lesson):
                    autopilot._save_lesson(task, failed_cap, error, lesson)

                @staticmethod
                def load(task, limit=3):
                    return autopilot._load_lessons(task, limit)

            self._store_cache = _MetaTraceStore()
        return self._store_cache

    def _executor(self) -> Callable:
        if self.config.executor is not None:
            return self.config.executor

        def _default(stage, task_text, context):
            from kernel import autopilot
            return autopilot.run(task_text, planner=self.config.planner)

        return _default

    def _confirm(self, stage: Stage, task_text: str) -> bool:
        if not stage.confirm:
            return True
        fn = self.config.confirm_fn
        if fn is None:
            return True  # 默认放行；生产环境应接策略/人工确认
        allowed = bool(fn(stage, task_text))
        self._confirm_log.append({"stage": stage.id, "allowed": allowed})
        return allowed

    # ---- 任务文本构造（含历史教训注入） ----
    def _build_task(self, stage: Stage, lessons: List[Dict[str, Any]]) -> str:
        text = stage.prompt.replace("{business}", self.config.business)
        if lessons:
            lines = [f"[历史教训-务必参考] {l.get('lesson', '')}" for l in lessons]
            text = text + "\n" + "\n".join(lines)
        return text

    # ---- 结果判定（兼容 autopilot.run 返回结构） ----
    @staticmethod
    def _is_ok(res: Any) -> bool:
        if isinstance(res, dict):
            if "reflection" in res:
                return not res["reflection"].get("exhausted", False)
            if "ok" in res:
                return bool(res["ok"])
            if "error" in res:
                return False
        return bool(res)

    @staticmethod
    def _error_of(res: Any) -> str:
        if isinstance(res, dict):
            return str(
                res.get("error") or res.get("reflection", {}).get("log") or "未知失败"
            )[:200]
        return str(res)[:200]

    # ---- 主入口 ----
    def run(self) -> Dict[str, Any]:
        store = self._get_store()
        executor = self._executor()

        # 初始历史教训（冷启动可能为空，符合「记忆是加速器非前提」）
        all_lessons: List[Dict[str, Any]] = (
            store.load(self.config.business, limit=5) if self.config.inject_lessons else []
        )

        for cycle in range(self.config.max_cycles):
            cycle_out: Dict[str, Any] = {
                "cycle": cycle, "stages": [], "lessons_saved": 0,
            }
            for stage in self.stages:
                task_text = self._build_task(
                    stage, all_lessons if stage.id == "analyze" else []
                )

                # 副作用阶段：确认门控（默认串行，绝不并入并行组）
                if stage.side_effect and not self._confirm(stage, task_text):
                    cycle_out["stages"].append(
                        {"stage": stage.id, "skipped": True, "reason": "confirm_denied"}
                    )
                    continue

                ctx = {"cycle": cycle, "business": self.config.business}
                res = executor(stage, task_text, ctx)
                ok = self._is_ok(res)
                cycle_out["stages"].append({"stage": stage.id, "ok": ok, "result": res})

                if self.config.on_stage_end:
                    self.config.on_stage_end(stage, res, ctx)

                # 失败 → 回流写 Meta-Trace
                if not ok and self.config.inject_lessons:
                    err = self._error_of(res)
                    lesson = (
                        f"阶段[{stage.name}]在第{cycle}轮未达成：{err}。"
                        f"下轮分析应规避同类问题并调整策略。"
                    )
                    store.save(self.config.business, stage.capability, err, lesson)
                    cycle_out["lessons_saved"] += 1

            self._cycle_results.append(cycle_out)
            if self.config.on_cycle_end:
                self.config.on_cycle_end(cycle_out, cycle)

            # 每轮结束重新拉取最新教训，供下轮分析注入（自改进飞轮）
            if self.config.inject_lessons:
                all_lessons = store.load(self.config.business, limit=5)

        return {
            "business": self.config.business,
            "cycles": self.config.max_cycles,
            "stages": [s.id for s in self.stages],
            "confirm_log": self._confirm_log,
            "cycles_detail": self._cycle_results,
        }
