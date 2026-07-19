"""内容飞轮技能 — 薄包装层，把 ContentFlywheel 引擎暴露为标准 Skill。

本文件不实现任何业务逻辑。所有能力（Forge→Cast→Echo→Refine + 反思闭环 +
EvolveEngine 反哺）均在 kernel.plugins.content_flywheel 引擎内完成。
本 Skill 仅负责：
  1. 接收 manifest 调度（execute(context)）
  2. 构建引擎实例并委托执行
  3. 格式化输出报告

用法：
    from skills.content_flywheel_skill import ContentFlywheelSkill
    skill = ContentFlywheelSkill(route_fn=hub.route)
    result = skill.execute({"topic": "AI 智能体", "max_cycles": 3})
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skills.base import Skill, SkillMeta


class ContentFlywheelSkill(Skill):
    """内容飞轮技能：委托 kernel.plugins.content_flywheel.ContentFlywheel 引擎。"""

    NAME = "content-flywheel"
    DESCRIPTION = "小团队内容自动化飞轮：Forge→Cast→Echo→Refine 循环 + 反思学习闭环"
    VERSION = "1.1.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "business"
    TAGS = ["content", "flywheel", "automation", "video", "social-media"]
    CAPABILITIES = ["content.produce", "content.publish", "content.feedback", "content.optimize"]

    def __init__(self, meta: Optional[SkillMeta] = None, route_fn=None):
        super().__init__(meta)
        self._route_fn = route_fn

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行内容飞轮。

        context 参数：
            topic: str — 内容主题（必填）
            max_cycles: int — 最大循环次数（默认 3，硬上限 20）
            platforms: List[str] — 分发平台（默认 ["douyin"]）
            style: str — 内容风格（默认 "douyin"）
            duration: int — 视频时长秒（默认 60）
            auto_publish: bool — 是否自动发布（默认 False）
            interval_seconds: int — 循环间隔（默认 0）
        """
        t0 = time.perf_counter()
        topic = context.get("topic", "").strip()
        if not topic:
            return {"success": False, "error": "缺少必填参数 topic（内容主题）"}

        max_cycles = min(int(context.get("max_cycles", 3)), 20)

        # 构建引擎配置
        config = {
            "max_cycles": max_cycles,
            "interval_seconds": int(context.get("interval_seconds", 0)),
            "platforms": context.get("platforms", ["douyin"]),
            "style": context.get("style", "douyin"),
            "duration": int(context.get("duration", 60)),
            "auto_publish": bool(context.get("auto_publish", False)),
        }

        # 委托引擎执行
        try:
            from kernel.plugins.content_flywheel import ContentFlywheel
            flywheel = ContentFlywheel(
                topic=topic, route_fn=self._route_fn, config=config,
            )
            cycles = []
            for _ in range(max_cycles):
                cycle_result = flywheel.run_once()
                cycles.append(cycle_result)
            state = flywheel.get_state()
        except Exception as e:
            return {
                "success": False,
                "error": f"ContentFlywheel 引擎执行失败: {e}",
                "elapsed_seconds": round(time.perf_counter() - t0, 2),
            }

        elapsed = time.perf_counter() - t0
        completed = sum(1 for c in cycles if c.get("status") == "completed")

        return {
            "success": True,
            "topic": topic,
            "final_topic": flywheel.topic,
            "total_cycles": len(cycles),
            "completed_cycles": completed,
            "cycles": cycles,
            "state": state,
            "elapsed_seconds": round(elapsed, 2),
            "trace": {
                "skill": self.NAME,
                "version": self.VERSION,
                "engine": "kernel.plugins.content_flywheel.ContentFlywheel",
                "topic": topic,
                "config": config,
                "total_cycles": len(cycles),
                "completed_cycles": completed,
                "elapsed_seconds": round(elapsed, 2),
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        }

    def format_report(self, result: Dict) -> str:
        """将执行结果格式化为人类可读报告。"""
        if not result.get("success"):
            return f"❌ 执行失败：{result.get('error', '未知错误')}"

        parts = [
            "=" * 60,
            "        内容飞轮执行报告",
            "=" * 60,
            "",
            f"主题：{result.get('topic', '?')}",
            f"循环：{result.get('completed_cycles', 0)}/{result.get('total_cycles', 0)} 轮完成",
            "",
        ]

        for cycle in result.get("cycles", []):
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

        parts.extend([
            "─" * 60,
            f"⏱ 耗时 {result.get('elapsed_seconds', 0)}s | 全链路可复核 ✓",
            "=" * 60,
        ])
        return "\n".join(parts)
