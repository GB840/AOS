"""内容飞轮自动化引擎（Content Flywheel）。

把 Forge → Cast → Echo → Refine 串成自动循环，
支持定时触发、循环次数限制、状态持久化。

设计原则：
- 可暂停/可恢复：状态持久化到磁盘，崩溃了下次接着跑
- 优雅降级：哪步失败了不影响整体，记下来继续
- 可观测：每一步都有日志、有指标、有历史记录
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_STATE_DIR = os.environ.get(
    "AOS_FLYWHEEL_STATE_DIR",
    os.path.join("data", "workspaces", "fabric", "flywheel"),
)


def _state_dir() -> str:
    os.makedirs(_STATE_DIR, exist_ok=True)
    return _STATE_DIR


@dataclass
class FlywheelCycle:
    """一轮循环的记录。"""
    cycle_id: str
    cycle_num: int
    topic: str
    started_at: str
    ended_at: str = ""
    status: str = "running"  # running / completed / failed / partial
    stages: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class FlywheelState:
    """飞轮整体状态。"""
    flywheel_id: str
    topic: str
    config: Dict[str, Any] = field(default_factory=dict)
    current_cycle: int = 0
    total_cycles: int = 0
    cycles: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ContentFlywheel:
    """内容飞轮引擎。

    用法：
        flywheel = ContentFlywheel(
            topic="AI 智能体",
            route_fn=hub.route,
            config={"max_cycles": 10, "interval_seconds": 3600},
        )
        flywheel.start()  # 启动后台循环
        flywheel.run_once()  # 或者手动跑一轮
    """

    def __init__(self, *, topic: str, route_fn=None, config: Dict = None):
        self.flywheel_id = uuid.uuid4().hex[:8]
        self.topic = topic
        self._route_fn = route_fn
        self.config = {
            "max_cycles": 10,           # 最多循环多少轮
            "interval_seconds": 3600,   # 每轮间隔（秒）
            "platforms": ["douyin", "xiaohongshu", "bilibili"],
            "style": "douyin",
            "duration": 60,
            "auto_publish": False,      # 是否自动发布（默认只生成包）
        }
        if config:
            self.config.update(config)

        self._state = FlywheelState(
            flywheel_id=self.flywheel_id,
            topic=topic,
            config=self.config,
            created_at=datetime.now().isoformat(),
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    # ── 公共 API ──

    def start(self) -> str:
        """启动后台循环线程。"""
        if self._thread and self._thread.is_alive():
            return "already running"

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return "started"

    def stop(self) -> str:
        """停止后台循环。"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        return "stopped"

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_once(self) -> Dict:
        """手动跑一轮。"""
        return self._run_cycle()

    def get_state(self) -> Dict:
        """获取当前状态。"""
        with self._lock:
            self._state.updated_at = datetime.now().isoformat()
            return asdict(self._state)

    def get_cycle(self, cycle_id: str) -> Optional[Dict]:
        """获取某一轮的详情。"""
        for c in self._state.cycles:
            if c.get("cycle_id") == cycle_id:
                return c
        return None

    # ── 内部实现 ──

    def _run_loop(self) -> None:
        """后台循环线程主函数。"""
        while not self._stop_event.is_set():
            if self._state.current_cycle >= self.config["max_cycles"]:
                logger.info("飞轮达到最大循环次数 %d，停止", self.config["max_cycles"])
                break

            try:
                self._run_cycle()
            except Exception as e:
                logger.error("飞轮循环异常: %s", e, exc_info=True)

            # 等待下一轮，支持中途停止
            interval = self.config["interval_seconds"]
            self._stop_event.wait(timeout=interval)
            if self._stop_event.is_set():
                break

    def _run_cycle(self) -> Dict:
        """执行一轮完整循环。"""
        with self._lock:
            self._state.current_cycle += 1
            self._state.total_cycles += 1
            cycle_num = self._state.current_cycle

        cycle = FlywheelCycle(
            cycle_id=uuid.uuid4().hex[:8],
            cycle_num=cycle_num,
            topic=self.topic,
            started_at=datetime.now().isoformat(),
        )

        logger.info("飞轮第 %d 轮开始: %s", cycle_num, self.topic)

        # 每一步都包 try/except，失败不影响整体
        try:
            # 1. Forge：内容生产
            cycle.stages["forge"] = self._stage_forge()
        except Exception as e:
            cycle.stages["forge"] = {"ok": False, "error": str(e)}
            logger.warning("Forge 阶段失败: %s", e)

        # 2. Cast：多平台分发
        try:
            video_path = ""
            script = ""
            if cycle.stages.get("forge", {}).get("ok"):
                video_path = cycle.stages["forge"].get("video_path", "")
                script = cycle.stages["forge"].get("script", "")
            cycle.stages["cast"] = self._stage_cast(video_path, script)
        except Exception as e:
            cycle.stages["cast"] = {"ok": False, "error": str(e)}
            logger.warning("Cast 阶段失败: %s", e)

        # 3. Echo：全网反馈采集
        try:
            cycle.stages["echo"] = self._stage_echo()
        except Exception as e:
            cycle.stages["echo"] = {"ok": False, "error": str(e)}
            logger.warning("Echo 阶段失败: %s", e)

        # 4. Refine：内容优化
        try:
            feedback_data = cycle.stages.get("echo", {}).get("data", {})
            cycle.stages["refine"] = self._stage_refine(feedback_data)
        except Exception as e:
            cycle.stages["refine"] = {"ok": False, "error": str(e)}
            logger.warning("Refine 阶段失败: %s", e)

        # 5. 为下一轮更新 topic（基于优化建议）
        try:
            refine_data = cycle.stages.get("refine", {}).get("data", {})
            next_plan = refine_data.get("next_content_plan", {})
            if next_plan and next_plan.get("topic"):
                self.topic = next_plan["topic"]
                logger.info("下一轮主题更新为: %s", self.topic)
        except Exception as e:
            logger.debug("更新下一轮主题失败: %s", e)

        # 记录状态
        cycle.ended_at = datetime.now().isoformat()
        ok_count = sum(1 for s in cycle.stages.values() if s.get("ok"))
        total = len(cycle.stages)
        if ok_count == total:
            cycle.status = "completed"
        elif ok_count > 0:
            cycle.status = "partial"
        else:
            cycle.status = "failed"

        with self._lock:
            cycle_dict = asdict(cycle)
            self._state.cycles.append(cycle_dict)
            self._state.updated_at = datetime.now().isoformat()
            # 只保留最近 50 轮
            if len(self._state.cycles) > 50:
                self._state.cycles = self._state.cycles[-50:]

        # 持久化
        self._save_state()

        # 上报到 Pulse（双飞轮打通：内容飞轮数据进产品飞轮）
        try:
            from kernel.pulse.pulse_collector import get_pulse_collector
            pulse = get_pulse_collector()
            duration = (datetime.fromisoformat(cycle.ended_at) - datetime.fromisoformat(cycle.started_at)).total_seconds()
            pulse.record_run(
                f"content_flywheel:{self.topic}",
                {
                    "status": cycle.status if cycle.status == "completed" else "failed",
                    "duration": duration,
                    "stages": {k: v.get("ok", False) for k, v in cycle.stages.items()},
                    "cycle_id": cycle.cycle_id,
                    "cycle_num": cycle.cycle_num,
                },
            )
            # 把 Echo 的反馈也上报
            echo_data = cycle.stages.get("echo", {}).get("data", {})
            if echo_data:
                pulse.record_feedback(
                    f"content_flywheel:{self.topic}",
                    {
                        "source": "echo",
                        "positive_count": echo_data.get("positive_count", 0),
                        "negative_count": echo_data.get("negative_count", 0),
                        "neutral_count": echo_data.get("neutral_count", 0),
                        "sample_count": echo_data.get("total", 0),
                    },
                )
        except Exception as e:
            logger.debug("Pulse 上报失败: %s", e)

        logger.info("飞轮第 %d 轮结束: %s (%d/%d 阶段成功)",
                    cycle_num, cycle.status, ok_count, total)

        return asdict(cycle)

    def _stage_forge(self) -> Dict:
        """Forge 阶段：内容生产。"""
        if not self._route_fn:
            return {"ok": False, "error": "无 route_fn"}

        res = self._route_fn("content.marketing_video", {
            "topic": self.topic,
            "style": self.config.get("style", "douyin"),
            "duration": self.config.get("duration", 60),
        })
        data = res.data if hasattr(res, "data") and res.ok else {}

        return {
            "ok": hasattr(res, "ok") and res.ok,
            "error": res.error if hasattr(res, "error") and not res.ok else "",
            "data": data,
            "video_path": data.get("video_path", ""),
            "script": data.get("script", ""),
            "stages": data.get("stages", []),
        }

    def _stage_cast(self, video_path: str, script: str) -> Dict:
        """Cast 阶段：多平台分发。"""
        if not self._route_fn:
            return {"ok": False, "error": "无 route_fn"}

        res = self._route_fn("content.publish", {
            "topic": self.topic,
            "video_path": video_path,
            "script": script,
            "platforms": self.config.get("platforms", ["douyin"]),
            "mode": "auto" if self.config.get("auto_publish") else "package",
        })
        data = res.data if hasattr(res, "data") and res.ok else {}

        return {
            "ok": hasattr(res, "ok") and res.ok,
            "error": res.error if hasattr(res, "error") and not res.ok else "",
            "data": data,
            "package_count": len(data.get("packages", [])),
            "packages": data.get("packages", []),
        }

    def _stage_echo(self) -> Dict:
        """Echo 阶段：反馈采集。"""
        if not self._route_fn:
            return {"ok": False, "error": "无 route_fn"}

        res = self._route_fn("content.feedback", {
            "keyword": self.topic,
            "max_results": 20,
        })
        data = res.data if hasattr(res, "data") and res.ok else {}

        return {
            "ok": hasattr(res, "ok") and res.ok,
            "error": res.error if hasattr(res, "error") and not res.ok else "",
            "data": data,
            "total_count": data.get("total_count", 0),
            "positive": data.get("positive_count", 0),
            "negative": data.get("negative_count", 0),
        }

    def _stage_refine(self, feedback_data: Dict) -> Dict:
        """Refine 阶段：内容优化。"""
        if not self._route_fn:
            return {"ok": False, "error": "无 route_fn"}

        res = self._route_fn("content.optimize", {
            "topic": self.topic,
            "feedback_data": feedback_data,
            "content_type": "video",
        })
        data = res.data if hasattr(res, "data") and res.ok else {}

        return {
            "ok": hasattr(res, "ok") and res.ok,
            "error": res.error if hasattr(res, "error") and not res.ok else "",
            "data": data,
            "suggestion_count": len(data.get("suggestions", [])),
            "next_plan": data.get("next_content_plan", {}),
        }

    def _save_state(self) -> None:
        """持久化状态到磁盘。"""
        try:
            path = os.path.join(_state_dir(), f"flywheel_{self.flywheel_id}.json")
            state_dict = self.get_state()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("保存飞轮状态失败: %s", e)
