"""内容飞轮技能 — AOS 第三商业场景：小团队内容自动化 + 反思闭环。

把已有的 ContentFlywheel 引擎（Forge→Cast→Echo→Refine）包装为标准 Skill，
并叠加跨会话反思学习：每轮循环的失败/低效自动提炼教训，下一轮自动注入。

设计原则（Ponytail 阶梯）：
- 复用 kernel.plugins.content_flywheel.ContentFlywheel（已有 384 行真实实现）
- 复用 kernel.evolve.evolve_engine.auto_apply_content_proposals（已有内容优化闭环）
- 教训持久化用 JSONL + threading.Lock + 有界轮转（与 bidding_agent 同模式）
- 全链路 trace 可复核（理念 8/9）
- 反思学习：每轮结果 → 提炼教训 → 下轮注入（理念 2 + 2.5）

用法：
    from skills.content_flywheel_skill import ContentFlywheelSkill
    skill = ContentFlywheelSkill()
    result = skill.execute({
        "topic": "AI 智能体",
        "max_cycles": 3,
        "platforms": ["douyin", "xiaohongshu"],
        "style": "douyin",
    })
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 教训持久化路径
# ---------------------------------------------------------------------------

_LESSONS_DIR = Path(os.environ.get(
    "AOS_FLYWHEEL_LESSONS_DIR",
    os.path.join("data", "workspaces", "fabric", "flywheel_lessons"),
))


# ---------------------------------------------------------------------------
# 反思提炼规则（结构化，非纯 LLM 猜测）
# ---------------------------------------------------------------------------

@dataclass
class ReflectionRule:
    """一条反思提炼规则：从循环结果中提取教训的条件。"""
    rule_id: str
    condition: str  # stage_failed / low_engagement / no_feedback / partial_cycle
    threshold: float = 0.0  # 数值阈值（如互动率低于此值）
    lesson_template: str = ""  # 教训模板
    severity: str = "medium"  # high / medium / low


REFLECTION_RULES: List[ReflectionRule] = [
    ReflectionRule(
        rule_id="R01",
        condition="stage_failed",
        lesson_template="阶段 {stage} 执行失败（{error}），下次应检查 {stage} 前置条件",
        severity="high",
    ),
    ReflectionRule(
        rule_id="R02",
        condition="low_engagement",
        threshold=5.0,
        lesson_template="主题「{topic}」互动量仅 {count}，低于阈值 {threshold}，应调整选题方向或内容形式",
        severity="medium",
    ),
    ReflectionRule(
        rule_id="R03",
        condition="no_feedback",
        lesson_template="Echo 阶段未采集到任何反馈数据，可能是分发渠道未生效或关键词不匹配",
        severity="medium",
    ),
    ReflectionRule(
        rule_id="R04",
        condition="partial_cycle",
        lesson_template="第 {cycle_num} 轮仅 {ok_count}/{total} 阶段成功，瓶颈在 {failed_stages}",
        severity="high",
    ),
    ReflectionRule(
        rule_id="R05",
        condition="topic_drift",
        lesson_template="主题从「{original_topic}」漂移到「{new_topic}」，需确认是否符合账号定位",
        severity="low",
    ),
    ReflectionRule(
        rule_id="R06",
        condition="repeated_failure",
        lesson_template="阶段 {stage} 连续 {count} 轮失败，应暂停飞轮排查根因而非继续循环",
        severity="high",
    ),
]


class ContentFlywheelSkill(Skill):
    """内容飞轮技能：自动化内容生产-分发-反馈-优化闭环 + 跨会话反思学习。"""

    NAME = "content-flywheel"
    DESCRIPTION = "小团队内容自动化飞轮：Forge→Cast→Echo→Refine 循环 + 反思学习闭环"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "business"
    TAGS = ["content", "flywheel", "automation", "video", "social-media"]
    CAPABILITIES = ["content.produce", "content.publish", "content.feedback", "content.optimize"]

    _MAX_LESSONS = 50  # 有界轮转上限

    def __init__(self, meta: Optional[SkillMeta] = None, route_fn=None):
        super().__init__(meta)
        self._route_fn = route_fn
        self._lessons_path = _LESSONS_DIR / "flywheel_lessons.jsonl"
        self._write_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行内容飞轮。

        context 参数：
            topic: str — 内容主题（必填）
            max_cycles: int — 最大循环次数（默认 3）
            platforms: List[str] — 分发平台（默认 ["douyin"]）
            style: str — 内容风格（默认 "douyin"）
            duration: int — 视频时长秒（默认 60）
            auto_publish: bool — 是否自动发布（默认 False）
            interval_seconds: int — 循环间隔（默认 0，即连续跑）
            inject_lessons: bool — 是否注入历史教训（默认 True）
        """
        t0 = time.perf_counter()
        topic = context.get("topic", "").strip()
        if not topic:
            return {"success": False, "error": "缺少必填参数 topic（内容主题）"}

        max_cycles = min(int(context.get("max_cycles", 3)), 20)  # 硬上限 20
        platforms = context.get("platforms", ["douyin"])
        style = context.get("style", "douyin")
        duration = int(context.get("duration", 60))
        auto_publish = bool(context.get("auto_publish", False))
        interval_seconds = int(context.get("interval_seconds", 0))
        inject_lessons = context.get("inject_lessons", True)

        # 1. 加载历史教训
        lessons = self._load_lessons(topic) if inject_lessons else []
        lesson_hints = [l.get("lesson", "") for l in lessons[-5:]]

        # 2. 构建飞轮配置
        config = {
            "max_cycles": max_cycles,
            "interval_seconds": interval_seconds,
            "platforms": platforms,
            "style": style,
            "duration": duration,
            "auto_publish": auto_publish,
        }

        # 3. 尝试获取真实 ContentFlywheel 引擎
        flywheel = self._get_flywheel(topic, config)
        if flywheel is None:
            # 降级：无 route_fn 时用模拟模式
            result = self._simulate_cycles(topic, config, lesson_hints)
        else:
            result = self._run_real_cycles(flywheel, topic, config, lesson_hints)

        # 4. 反思提炼：从结果中提取教训
        new_lessons = self._reflect(result, topic)
        for lesson_text in new_lessons:
            self.save_lesson(lesson_text, context=f"topic={topic}")

        # 5. 尝试触发 EvolveEngine 内容优化提案
        evolve_applied = self._try_evolve(topic)

        elapsed = time.perf_counter() - t0
        result["elapsed_seconds"] = round(elapsed, 2)
        result["lessons_injected"] = len(lesson_hints)
        result["lessons_extracted"] = len(new_lessons)
        result["evolve_proposals_applied"] = evolve_applied
        result["trace"] = self._build_trace(result, topic, config)

        return result

    # ------------------------------------------------------------------
    # 真实飞轮执行
    # ------------------------------------------------------------------

    def _get_flywheel(self, topic: str, config: Dict) -> Any:
        """尝试构建真实 ContentFlywheel 实例。"""
        if self._route_fn is None:
            return None
        try:
            from kernel.plugins.content_flywheel import ContentFlywheel
            return ContentFlywheel(topic=topic, route_fn=self._route_fn, config=config)
        except Exception as e:
            self._log.warning("ContentFlywheel 构建失败，降级为模拟模式: %s", e)
            return None

    def _run_real_cycles(self, flywheel, topic: str, config: Dict,
                         lesson_hints: List[str]) -> Dict:
        """用真实飞轮跑循环。"""
        cycles = []
        for i in range(config["max_cycles"]):
            try:
                cycle_result = flywheel.run_once()
                cycles.append(cycle_result)
            except Exception as e:
                cycles.append({
                    "cycle_num": i + 1,
                    "status": "failed",
                    "error": str(e),
                    "stages": {},
                })
            # 如果主题被 refine 更新了，记录
            if hasattr(flywheel, "topic") and flywheel.topic != topic:
                topic = flywheel.topic

        state = flywheel.get_state() if hasattr(flywheel, "get_state") else {}
        return {
            "success": True,
            "mode": "real",
            "topic": topic,
            "cycles": cycles,
            "total_cycles": len(cycles),
            "completed_cycles": sum(1 for c in cycles if c.get("status") == "completed"),
            "state": state,
        }

    # ------------------------------------------------------------------
    # 模拟模式（无 route_fn 时的降级路径，保证 Skill 可独立演示）
    # ------------------------------------------------------------------

    def _simulate_cycles(self, topic: str, config: Dict,
                         lesson_hints: List[str]) -> Dict:
        """模拟飞轮循环（用于演示/测试，不依赖外部引擎）。"""
        cycles = []
        current_topic = topic

        for i in range(config["max_cycles"]):
            cycle = {
                "cycle_num": i + 1,
                "topic": current_topic,
                "status": "completed",
                "stages": {
                    "forge": {
                        "ok": True,
                        "script": f"[模拟] 关于「{current_topic}」的{config['style']}风格短视频脚本",
                        "video_path": f"[模拟] {current_topic}_ep{i+1}.mp4",
                    },
                    "cast": {
                        "ok": True,
                        "package_count": len(config["platforms"]),
                        "packages": [
                            {"platform": p, "status": "packaged"}
                            for p in config["platforms"]
                        ],
                    },
                    "echo": {
                        "ok": True,
                        "total_count": 15 + i * 8,
                        "positive": 10 + i * 5,
                        "negative": 2,
                    },
                    "refine": {
                        "ok": True,
                        "suggestion_count": 2,
                        "next_plan": {
                            "topic": self._next_topic(current_topic, i),
                            "adjustments": ["增加实操演示", "缩短开头铺垫"],
                        },
                    },
                },
            }
            # 模拟教训注入效果：如果有历史教训，调整内容
            if lesson_hints and i == 0:
                cycle["stages"]["forge"]["lesson_applied"] = lesson_hints[-1]

            cycles.append(cycle)
            # 主题演进
            next_plan = cycle["stages"]["refine"].get("next_plan", {})
            if next_plan.get("topic"):
                current_topic = next_plan["topic"]

        return {
            "success": True,
            "mode": "simulated",
            "topic": topic,
            "final_topic": current_topic,
            "cycles": cycles,
            "total_cycles": len(cycles),
            "completed_cycles": len(cycles),
            "note": "模拟模式：未连接真实引擎，结果仅供演示",
        }

    def _next_topic(self, topic: str, cycle_idx: int) -> str:
        """模拟主题演进逻辑。"""
        evolutions = [
            f"{topic}实操教程",
            f"{topic}避坑指南",
            f"{topic}成本对比",
            f"{topic}未来趋势",
        ]
        return evolutions[cycle_idx % len(evolutions)]

    # ------------------------------------------------------------------
    # 反思提炼（结构化规则，非纯 LLM）
    # ------------------------------------------------------------------

    def _reflect(self, result: Dict, original_topic: str) -> List[str]:
        """从飞轮结果中提炼教训。"""
        lessons: List[str] = []
        cycles = result.get("cycles", [])
        if not cycles:
            return lessons

        # 统计各阶段失败次数
        stage_failures: Dict[str, int] = {}
        for cycle in cycles:
            stages = cycle.get("stages", {})
            for stage_name, stage_data in stages.items():
                if isinstance(stage_data, dict) and not stage_data.get("ok", True):
                    stage_failures[stage_name] = stage_failures.get(stage_name, 0) + 1

        for rule in REFLECTION_RULES:
            if rule.condition == "stage_failed":
                for stage_name, count in stage_failures.items():
                    if count >= 1:
                        error = ""
                        for c in cycles:
                            sd = c.get("stages", {}).get(stage_name, {})
                            if isinstance(sd, dict) and sd.get("error"):
                                error = sd["error"][:100]
                                break
                        lessons.append(rule.lesson_template.format(
                            stage=stage_name, error=error or "未知错误"))

            elif rule.condition == "low_engagement":
                for cycle in cycles:
                    echo = cycle.get("stages", {}).get("echo", {})
                    if isinstance(echo, dict) and echo.get("ok"):
                        total = echo.get("total_count", 0)
                        if 0 < total < rule.threshold:
                            lessons.append(rule.lesson_template.format(
                                topic=cycle.get("topic", original_topic),
                                count=total,
                                threshold=rule.threshold))

            elif rule.condition == "no_feedback":
                for cycle in cycles:
                    echo = cycle.get("stages", {}).get("echo", {})
                    if isinstance(echo, dict) and echo.get("ok"):
                        if echo.get("total_count", 0) == 0:
                            lessons.append(rule.lesson_template)
                            break

            elif rule.condition == "partial_cycle":
                for cycle in cycles:
                    stages = cycle.get("stages", {})
                    if not stages:
                        continue
                    ok_count = sum(
                        1 for s in stages.values()
                        if isinstance(s, dict) and s.get("ok")
                    )
                    total = len(stages)
                    if 0 < ok_count < total:
                        failed = [
                            name for name, s in stages.items()
                            if isinstance(s, dict) and not s.get("ok")
                        ]
                        lessons.append(rule.lesson_template.format(
                            cycle_num=cycle.get("cycle_num", "?"),
                            ok_count=ok_count,
                            total=total,
                            failed_stages=", ".join(failed)))

            elif rule.condition == "topic_drift":
                final_topic = result.get("final_topic", "")
                if final_topic and final_topic != original_topic:
                    lessons.append(rule.lesson_template.format(
                        original_topic=original_topic,
                        new_topic=final_topic))

            elif rule.condition == "repeated_failure":
                for stage_name, count in stage_failures.items():
                    if count >= 2:
                        lessons.append(rule.lesson_template.format(
                            stage=stage_name, count=count))

        # 去重
        seen: set = set()
        unique: List[str] = []
        for l in lessons:
            if l not in seen:
                seen.add(l)
                unique.append(l)
        return unique[:10]  # 单次最多提炼 10 条

    # ------------------------------------------------------------------
    # EvolveEngine 联动
    # ------------------------------------------------------------------

    def _try_evolve(self, topic: str) -> int:
        """尝试触发 EvolveEngine 内容优化提案（优雅降级）。"""
        try:
            from kernel.evolve.evolve_engine import get_evolve_engine
            engine = get_evolve_engine()
            applied = engine.auto_apply_content_proposals(topic)
            return len(applied)
        except Exception as e:
            self._log.debug("EvolveEngine 联动跳过: %s", e)
            return 0

    # ------------------------------------------------------------------
    # 教训持久化（与 bidding_agent 同模式：Lock + 有界轮转）
    # ------------------------------------------------------------------

    def _load_lessons(self, topic: str = "") -> List[Dict]:
        """加载历史内容飞轮教训。"""
        if not self._lessons_path.exists():
            return []
        lessons = []
        try:
            for line in self._lessons_path.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        lessons.append(json.loads(line))
                    except json.JSONDecodeError:
                        self._log.warning("教训文件含损坏行，已跳过: %.40s", line)
        except Exception as e:
            self._log.warning("教训文件读取失败: %s", e)
        return lessons[-20:]

    def save_lesson(self, lesson: str, context: str = ""):
        """保存一条内容飞轮教训（有锁 + 有界轮转）。"""
        if not lesson or len(lesson.strip()) < 5:
            return
        with self._write_lock:
            self._lessons_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "lesson": lesson[:500],
                "context": context[:200],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self._lessons_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # 有界轮转
            try:
                lines = self._lessons_path.read_text(encoding="utf-8").strip().split("\n")
                if len(lines) > self._MAX_LESSONS:
                    keep = lines[-self._MAX_LESSONS:]
                    self._lessons_path.write_text(
                        "\n".join(keep) + "\n", encoding="utf-8")
            except Exception:
                pass
        self._log.info("教训已保存: %s", lesson[:50])

    # ------------------------------------------------------------------
    # Trace 构建（理念 8/9：全链路可复核）
    # ------------------------------------------------------------------

    def _build_trace(self, result: Dict, topic: str, config: Dict) -> Dict:
        """构建可复核的执行 trace。"""
        return {
            "skill": self.NAME,
            "version": self.VERSION,
            "topic": topic,
            "config": config,
            "mode": result.get("mode", "unknown"),
            "total_cycles": result.get("total_cycles", 0),
            "completed_cycles": result.get("completed_cycles", 0),
            "lessons_injected": result.get("lessons_injected", 0),
            "lessons_extracted": result.get("lessons_extracted", 0),
            "evolve_applied": result.get("evolve_proposals_applied", 0),
            "elapsed_seconds": result.get("elapsed_seconds", 0),
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # 报告格式化
    # ------------------------------------------------------------------

    def format_report(self, result: Dict) -> str:
        """将执行结果格式化为人类可读报告。"""
        parts = [
            "=" * 60,
            "        内容飞轮执行报告",
            "=" * 60,
            "",
            f"主题：{result.get('topic', '?')}",
            f"模式：{'真实引擎' if result.get('mode') == 'real' else '模拟演示'}",
            f"循环：{result.get('completed_cycles', 0)}/{result.get('total_cycles', 0)} 轮完成",
            "",
        ]

        # 各轮详情
        cycles = result.get("cycles", [])
        for cycle in cycles:
            num = cycle.get("cycle_num", "?")
            status = cycle.get("status", "?")
            icon = {"completed": "✅", "partial": "⚠️", "failed": "❌"}.get(status, "❓")
            parts.append(f"  {icon} 第 {num} 轮 [{status}]")
            stages = cycle.get("stages", {})
            for stage_name in ["forge", "cast", "echo", "refine"]:
                sd = stages.get(stage_name, {})
                if isinstance(sd, dict):
                    ok = sd.get("ok", False)
                    stage_icon = "✓" if ok else "✗"
                    detail = ""
                    if stage_name == "forge" and sd.get("script"):
                        detail = f" — {sd['script'][:40]}"
                    elif stage_name == "cast":
                        detail = f" — {sd.get('package_count', 0)} 个平台包"
                    elif stage_name == "echo":
                        detail = f" — 互动 {sd.get('total_count', 0)} 条"
                    elif stage_name == "refine":
                        detail = f" — {sd.get('suggestion_count', 0)} 条优化建议"
                    parts.append(f"     {stage_icon} {stage_name}{detail}")
            parts.append("")

        # 教训
        if result.get("lessons_injected", 0) > 0:
            parts.append(f"📚 注入历史教训 {result['lessons_injected']} 条")
        if result.get("lessons_extracted", 0) > 0:
            parts.append(f"💡 本轮提炼教训 {result['lessons_extracted']} 条")
        if result.get("evolve_proposals_applied", 0) > 0:
            parts.append(f"🔄 EvolveEngine 自动应用 {result['evolve_proposals_applied']} 条优化")

        parts.extend([
            "",
            "─" * 60,
            f"⏱ 耗时 {result.get('elapsed_seconds', 0)}s | "
            f"循环 {result.get('total_cycles', 0)} 轮 | 全链路可复核 ✓",
            "=" * 60,
        ])
        return "\n".join(parts)
