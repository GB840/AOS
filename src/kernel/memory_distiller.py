"""常驻记忆提炼 Agent（借鉴 Jcode 的常驻记忆提炼思路）。

问题背景：AOS 的理念9（白盒才可进化）要求 structured JSON Trace 落盘 → 记忆系统
自动提炼。此前 trace 只落盘不提炼，缺一个「常驻、周期、自动」的提炼层。

本模块提供 MemoryDistiller：
- 周期扫描 AOS 的 trace 落盘（trace_*.json + route_outcomes.jsonl）
- 提炼可复用事实：失败模式 / 能力可靠性 / 延迟事实（均量化，对齐理念6）
- 持久化双通道：
  * 主通道：本地 _traces/distilled_memory.jsonl（始终可用，白盒进化根基）
  * 增强通道：mem0（经 Mem0Store，尊重 AOS_MEM0_LOCAL；不可用时自动降级，
    不影响主通道）
- 防重复提炼：记录已处理文件指纹（路径+大小+mtime）
- 常驻运行：run_loop() 是 asyncio 周期循环，复用 main.py 的 create_task 范式

设计原则：
- 诚实+量化：每条提炼带 confidence（按样本数三级：低<2 / 中2-4 / 高>=5）与来源，
  不编造（理念6）。
- best-effort、零阻塞：扫描/写入任何异常都被吞掉并记日志，绝不拖垮主进程。
- 不引外部依赖：纯标准库 + 复用现有 mem0_store / trace 落盘契约。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _default_trace_dirs() -> List[str]:
    here = os.path.abspath(__file__)
    src_dir = os.path.dirname(os.path.dirname(here))      # .../src
    repo_root = os.path.dirname(src_dir)                  # .../
    candidates = [
        os.path.join(src_dir, "_traces"),
        os.path.join(repo_root, "_traces"),
    ]
    return [c for c in candidates if os.path.isdir(c)]


@dataclass
class DistilledMemory:
    text: str
    category: str          # failure_pattern | capability_reliability | latency_fact
    source: str
    confidence: float      # 0..1，按样本数三级（低<2 / 中2-4 / 高>=5）
    metadata: Dict[str, Any] = field(default_factory=dict)
    ts: str = ""

    def to_record(self) -> Dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts or time.strftime("%Y-%m-%dT%H:%M:%S")
        return d


@dataclass
class DistillReport:
    scanned_files: int = 0
    new_items: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _confidence_for(n: int) -> float:
    if n >= 5:
        return 0.9
    if n >= 2:
        return 0.6
    return 0.3


class MemoryDistiller:
    def __init__(self, trace_dirs: Optional[List[str]] = None,
                 interval_seconds: int = 300, user_id: str = "aos",
                 out_path: Optional[str] = None,
                 state_path: Optional[str] = None,
                 mem0_store: Any = None, mem0_lazy: bool = False):
        self.trace_dirs = (trace_dirs or _default_trace_dirs()
                           or [os.path.join(os.getcwd(), "_traces")])
        self.interval = interval_seconds
        self.user_id = user_id
        self.out_path = out_path or self._default_out()
        self.state_path = state_path or self._default_state()
        self._mem0_store = mem0_store
        # mem0 增强通道三态：显式禁用 / 直接持有 / 待惰性构造（避免启动期重型 import）
        if mem0_store is not None:
            self._mem0_disabled = False
            self._mem0_pending = False
        elif mem0_lazy:
            self._mem0_disabled = False
            self._mem0_pending = True
        else:
            self._mem0_disabled = True
            self._mem0_pending = False
        self._processed: Dict[str, str] = self._load_state()
        self._lock = threading.Lock()
        self.running = False
        os.makedirs(os.path.dirname(self.out_path) or ".", exist_ok=True)

    # ---- 路径 ----
    def _default_out(self) -> str:
        d = self.trace_dirs[0]
        return os.path.join(d, "distilled_memory.jsonl")

    def _default_state(self) -> str:
        d = self.trace_dirs[0]
        return os.path.join(d, ".distill_state.json")

    # ---- 状态防重 ----
    def _fingerprint(self, path: str) -> str:
        try:
            st = os.stat(path)
            key = f"{path}:{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            key = path
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def _load_state(self) -> Dict[str, str]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self._processed, f)
        except OSError as e:
            logger.warning("distill state save failed: %s", e)

    # ---- 扫描主流程 ----
    def scan_once(self) -> DistillReport:
        report = DistillReport()
        collected: List[DistilledMemory] = []
        for d in self.trace_dirs:
            try:
                names = sorted(os.listdir(d))
            except OSError as e:
                report.errors.append(f"listdir {d}: {e}")
                continue
            for name in names:
                path = os.path.join(d, name)
                fp = self._fingerprint(path)
                if fp in self._processed:
                    continue
                try:
                    if name.startswith("trace_") and name.endswith(".json"):
                        items = self._distill_trace_file(path)
                        collected.extend(items)
                        report.scanned_files += 1
                        self._processed[fp] = name
                    elif name == "route_outcomes.jsonl":
                        items = self._distill_route_outcomes(path)
                        collected.extend(items)
                        report.scanned_files += 1
                        self._processed[fp] = name
                except Exception as e:  # noqa: BLE001
                    report.errors.append(f"{name}: {e}")
                    logger.warning("distill file failed %s: %s", name, e)
        if collected:
            self._persist(collected)
            report.new_items = len(collected)
            for it in collected:
                report.by_category[it.category] = report.by_category.get(it.category, 0) + 1
        self._save_state()
        return report

    # ---- 提炼：trace ----
    def _distill_trace_file(self, path: str) -> List[DistilledMemory]:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items: List[DistilledMemory] = []
        task = (data.get("input") or {}).get("task") or data.get("task_id") or "未知任务"
        steps = data.get("steps") or []
        metrics = data.get("metrics") or {}

        # 失败模式
        for s in steps:
            if s.get("ok"):
                continue
            cap = s.get("capability") or "未知能力"
            err = s.get("error") or "无错误信息"
            items.append(DistilledMemory(
                text=f"失败模式：能力「{cap}」在任务「{task}」中执行失败——{err}",
                category="failure_pattern",
                source=os.path.basename(path),
                confidence=_confidence_for(1),
                metadata={"task": task, "capability": cap, "error": err,
                          "kind": "trace_step_failure"},
            ))

        # 能力可靠性（按 capability 聚合 ok 率）
        agg: Dict[str, List[bool]] = {}
        for s in steps:
            cap = s.get("capability") or "未知能力"
            agg.setdefault(cap, []).append(bool(s.get("ok")))
        for cap, flags in agg.items():
            ok = sum(flags)
            total = len(flags)
            items.append(DistilledMemory(
                text=f"能力可靠性：能力「{cap}」在 trace 样本中成功率 {ok}/{total}（{ok/total:.0%}）",
                category="capability_reliability",
                source=os.path.basename(path),
                confidence=_confidence_for(total),
                metadata={"capability": cap, "ok": ok, "total": total},
            ))

        # 延迟事实
        lat = metrics.get("latency_ms")
        if lat is not None:
            items.append(DistilledMemory(
                text=f"延迟事实：任务「{task}」端到端耗时 {lat}ms",
                category="latency_fact",
                source=os.path.basename(path),
                confidence=_confidence_for(1),
                metadata={"task": task, "latency_ms": lat},
            ))
        return items

    # ---- 提炼：route_outcomes ----
    def _distill_route_outcomes(self, path: str) -> List[DistilledMemory]:
        rows: List[Dict[str, Any]] = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if not rows:
            return []

        agg: Dict[str, List[bool]] = {}
        for r in rows:
            key = f"{r.get('capability')}/{r.get('engine')}"
            agg.setdefault(key, []).append(bool(r.get("ok")))

        items: List[DistilledMemory] = []
        for key, flags in agg.items():
            ok = sum(flags)
            total = len(flags)
            items.append(DistilledMemory(
                text=f"路由可靠性：能力/引擎「{key}」成功率 {ok}/{total}（{ok/total:.0%}）",
                category="capability_reliability",
                source=os.path.basename(path),
                confidence=_confidence_for(total),
                metadata={"key": key, "ok": ok, "total": total},
            ))
        for r in rows:
            if r.get("ok"):
                continue
            cap = r.get("capability") or "未知能力"
            eng = r.get("engine") or "未知引擎"
            err = r.get("error") or "无错误"
            items.append(DistilledMemory(
                text=f"失败模式：路由「{cap}」经引擎「{eng}」失败——{err}",
                category="failure_pattern",
                source=os.path.basename(path),
                confidence=_confidence_for(1),
                metadata={"capability": cap, "engine": eng, "error": err},
            ))
        return items

    # ---- 持久化 ----
    def _persist(self, items: List[DistilledMemory]) -> None:
        with self._lock:
            try:
                with open(self.out_path, "a", encoding="utf-8") as f:
                    for it in items:
                        f.write(json.dumps(it.to_record(), ensure_ascii=False) + "\n")
            except OSError as e:
                logger.warning("distill persist failed: %s", e)
        if not self._mem0_disabled and self._mem0_store is not None:
            for it in items:
                self._try_mem0_add(it)

    def _try_mem0_add(self, item: DistilledMemory) -> bool:
        if self._mem0_pending:
            # 惰性构造 Mem0Store（尊重 AOS_MEM0_LOCAL；不可用时抛错→禁用通道）
            try:
                from core.memory.mem0_store import Mem0Store
                self._mem0_store = Mem0Store()
                self._mem0_pending = False
            except Exception as e:  # noqa: BLE001
                logger.warning("Mem0Store 惰性构造失败，禁用 mem0 通道: %s", e)
                self._mem0_disabled = True
                self._mem0_pending = False
                return False
        if self._mem0_disabled or self._mem0_store is None:
            return False
        try:
            self._mem0_store.add(item.text, user_id=self.user_id, metadata=item.metadata)
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 distill add failed, disabling channel: %s", e)
            self._mem0_disabled = True
            return False

    # ---- 常驻循环 ----
    async def run_loop(self) -> None:
        self.running = True
        logger.info("MemoryDistiller 常驻循环启动（间隔 %ss）", self.interval)
        while self.running:
            try:
                rep = self.scan_once()
                if rep.new_items:
                    logger.info("MemoryDistiller 提炼 %d 条记忆：%s",
                                rep.new_items, rep.by_category)
            except Exception as e:  # noqa: BLE001
                logger.warning("distill scan error: %s", e)
            await asyncio.sleep(self.interval)


# ---- 单例（供 main.py 接入）----
_distiller_instance: Optional[MemoryDistiller] = None


def get_distiller(trace_dirs: Optional[List[str]] = None,
                  interval_seconds: int = 300,
                  mem0_store: Any = None) -> MemoryDistiller:
    """返回常驻提炼 Agent 单例。mem0_store 不传时启用惰性通道（首次真正写记忆
    时才构造 Mem0Store，尊重 AOS_MEM0_LOCAL；不可用时自动降级为仅 jsonl 落盘），
    避免在进程启动/导入期触发重型 mem0/chroma import。"""
    global _distiller_instance
    if _distiller_instance is None:
        _distiller_instance = MemoryDistiller(
            trace_dirs=trace_dirs, interval_seconds=interval_seconds,
            mem0_store=mem0_store, mem0_lazy=(mem0_store is None))
    return _distiller_instance
