"""v1.0 Agent 运行时层：记忆管理 / 工作流编排 / Agent 生命周期管理。

这是 v1.0 物种思维中"Agent 运行时层（可换引擎）"的默认实现。
层级的抽象接口是 AgentRuntime(ABC)（定义在 ../interfaces.py）。
本层在其上叠加三个子组件：记忆管理、工作流编排、生命周期管理。

记忆管理使用 MemoryManager(ABC) + InMemoryMemoryManager 实现，
可插拔为 mem0 / ChromaDB / 未来任意记忆后端。
工作流编排用 asyncio.gather 真并发执行多步骤（解决旧 swarm_flow 串行问题）。
生命周期管理委托给 AOSKernel（create/start/stop/destroy）。

依赖倒置：本层依赖 AgentRuntime ABC + AOSKernel + stdlib，不 import 具体引擎。
换引擎只需换传入的 runtime 实例，本层逻辑不变。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..interfaces import AgentRuntime
from ..kernel import AOSKernel
from ..types import AgentInstance, AgentSpec, AgentStatus, Response

logger = logging.getLogger(__name__)


def _safe_async_run(coro):
    """安全地在同步上下文中运行协程：如果已有事件循环在运行则创建新循环在线程中执行。"""
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # 已在事件循环中（如 asyncio.to_thread），在新线程中创建独立循环
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# ─── 记忆管理器接口 + 默认实现 ──────────────────────────────────

class MemoryManager(ABC):
    """可插拔记忆管理器。默认实现 InMemoryMemoryManager，可替换为
    mem0.py / src/memory/vector_store / ChromaDB / 等任何后端。"""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        ...

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...

    @abstractmethod
    def keys(self) -> List[str]:
        """返回所有记忆键（用于按 agent 命名空间精确清理）。"""

    @abstractmethod
    def remove(self, key: str) -> None:
        """删除单个记忆键，不触碰其他 agent 的记忆。"""


class InMemoryMemoryManager(MemoryManager):
    """进程内字典记忆后端（零依赖，默认值）。

    可无缝替换为 ChromaDB / mem0 / Pinecone / 等实现了 MemoryManager 的类。
    """

    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = query.lower()
        with self._lock:
            results: List[tuple[int, Any]] = []
            for k, v in self._store.items():
                if q in str(k).lower():
                    results.append((0, {"key": k, "value": v}))
                elif isinstance(v, str) and q in v.lower():
                    results.append((1, {"key": k, "value": v}))
            results.sort(key=lambda x: x[0])
            return [r[1] for r in results[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._store.keys())

    def remove(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class FileMemoryManager(MemoryManager):
    """文件持久化记忆后端（JSON行格式，重启不丢失）。

    每次 set 写入一行 JSON，每行一个 key-value。
    适合个人本地部署、无需额外数据库。
    可无缝替换为 SQLite/Redis/等实现了 MemoryManager 的类。
    """

    # 理念8「限最大存储条数防磁盘打满」：.aos_memory.jsonl 上限。
    # 与 trace_store._MAX_TRACE_FILES=500 同源纪律。set 是 append-only（同 key
    # 多次写留多行旧值），_load 全文件读。上限 1000 行，达上限 compact：基于
    # _store 内存视图重写，每 key 只留最新值（去重，与 controllable_memory 同策略）。
    _MAX_LINES = 1000
    _TRIM_CHECK_EVERY = 50

    def __init__(self, filepath: str = ".aos_memory.jsonl") -> None:
        self._filepath = filepath
        self._store: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()
        # 理念8 轮转计数器（_compact 触发节流）
        self._since_last_trim = 0

    def _load(self) -> None:
        with self._lock:
            import json
            import os
            if not os.path.exists(self._filepath):
                return
            try:
                with open(self._filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            if "k" in entry:
                                self._store[entry["k"]] = entry.get("v")
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass

    def _save(self, key: str, value: Any) -> None:
        with self._lock:
            import json
            entry = json.dumps({"k": key, "v": value}, ensure_ascii=False,
                               default=str)
            try:
                with open(self._filepath, "a", encoding="utf-8") as f:
                    f.write(entry + "\n")
            except OSError:
                pass

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value
            self._save(key, value)
            # 理念8：防磁盘打满的节流 compact（同 key 多次写会留多行旧值）
            self._since_last_trim += 1
            if self._since_last_trim >= self._TRIM_CHECK_EVERY:
                self._since_last_trim = 0
                self._compact()

    def _compact(self) -> None:
        """达 _MAX_LINES 上限时基于 _store 重写文件，每 key 只留最新值（去重）。"""
        import json as _json
        import os as _os
        try:
            if not _os.path.exists(self._filepath):
                return
            with open(self._filepath, "r", encoding="utf-8") as f:
                count = sum(1 for ln in f if ln.strip())
            if count < self._MAX_LINES:
                return
            # _store 已是每 key 最新值（同 key 后写覆盖前写），直接重写
            tmp = self._filepath + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                for k, v in self._store.items():
                    f.write(_json.dumps({"k": k, "v": v}, ensure_ascii=False,
                                        default=str) + "\n")
            _os.replace(tmp, self._filepath)
        except Exception:  # noqa: BLE001 - compact 失败不致命
            pass

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = query.lower()
        results: List[tuple[int, Any]] = []
        for k, v in self._store.items():
            if q in str(k).lower():
                results.append((0, {"key": k, "value": v}))
            elif isinstance(v, str) and q in v.lower():
                results.append((1, {"key": k, "value": v}))
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results[:limit]]

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            import os
            try:
                os.remove(self._filepath)
            except OSError:
                pass

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._store.keys())

    def remove(self, key: str) -> None:
        if key in self._store:
            del self._store[key]
            self._rewrite()

    def _rewrite(self) -> None:
        with self._lock:
            import json
            try:
                with open(self._filepath, "w", encoding="utf-8") as f:
                    for k, v in self._store.items():
                        f.write(json.dumps({"k": k, "v": v}, ensure_ascii=False,
                                           default=str) + "\n")
            except OSError:
                pass


# ─── 工作流步骤 ─────────────────────────────────────────────────

@dataclass
class WorkflowStep:
    """工作流的一个步骤：指定 agent 执行一个任务。"""
    agent_id: str
    task: Dict[str, Any]  # 传给 AgentRuntime.run_agent 的 task
    step_id: str = ""
    depends_on: List[str] = field(default_factory=list)  # 依赖的前置 step_id

    def __post_init__(self) -> None:
        if not self.step_id:
            self.step_id = f"step-{self.agent_id}-{id(self)}"


@dataclass
class WorkflowResult:
    step_id: str
    agent_id: str
    response: Response
    elapsed_seconds: float = 0.0


# ─── Agent 运行时层 ──────────────────────────────────────────────

class AgentRuntimeLayer:
    """v1.0 Agent 运行时层（可换引擎）。

    三个子组件：
    1. 记忆管理 → memory: MemoryManager（可插拔）
    2. 工作流编排 → run_workflow(steps)（asyncio.gather 真并发）
    3. 生命周期管理 → register/list/stop → 委托内核
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        kernel: AOSKernel,
        memory: MemoryManager | None = None,
    ) -> None:
        self._runtime = runtime
        self._kernel = kernel
        self.memory: MemoryManager = memory or InMemoryMemoryManager()

    # ── 记忆管理 ──
    def remember(self, key: str, value: Any) -> None:
        self.memory.set(key, value)

    def recall(self, key: str) -> Optional[Any]:
        return self.memory.get(key)

    def search_memory(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return self.memory.search(query, limit)

    # ── 生命周期管理（委托内核） ──
    def create_agent(self, spec: AgentSpec) -> AgentInstance:
        inst = self._kernel.register_agent(spec)
        inst.status = AgentStatus.RUNNING
        return inst

    def list_agents(self) -> List[AgentInstance]:
        return self._kernel.list_agents()

    def stop_agent(self, agent_id: str) -> None:
        self._kernel.stop_agent(agent_id)
        # 仅清理该 agent 命名空间下的记忆（键形如 "agent_id:..."）。
        # 旧实现循环调用 self.memory.clear() 会把所有 agent 的全局记忆一并清空，
        # 此处改为按键精确删除（理念：故障隔离——停一个 agent 不影响其他）。
        prefix = f"{agent_id}:"
        removed = 0
        for k in self.memory.keys():
            if prefix in str(k):
                try:
                    self.memory.remove(k)
                    removed += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("清理 agent %s 记忆键 %s 失败: %s", agent_id, k, exc)
        logger.info("stop_agent 清理记忆键 %d 个（agent=%s）", removed, agent_id)

    # ── 工作流编排（真并发） ──
    def run_workflow(self, steps: List[WorkflowStep],
                     timeout_seconds: float = 300.0) -> List[WorkflowResult]:
        """同步入口：asyncio.gather 真并发编排多个 agent 步骤。

        这是对旧 swarm_flow 串行 execute_parallel() 的物种化替代：
        - 内核只负责路由/权限，编排逻辑在本层。
        - 用 asyncio.gather 真并发，而非串行 for 循环。
        - 支持 depends_on 声明步骤依赖（未依赖的步骤全部并发）。

        调用方若已在 asyncio event loop 中，请用 run_workflow_async()。
        """
        # 使用 _safe_async_run 避免在已有事件循环中调用 asyncio.run() 导致 RuntimeError
        return _safe_async_run(self.run_workflow_async(steps, timeout_seconds))

    async def run_workflow_async(self, steps: List[WorkflowStep],
                                 timeout_seconds: float = 300.0) -> List[WorkflowResult]:
        """异步入口：asyncio.gather 真并发编排。"""

        # 拓扑排序：只有无依赖或依赖已完成的步骤才能执行
        results: Dict[str, WorkflowResult] = {}
        pending = list(steps)

        async def _execute_one(step: WorkflowStep) -> WorkflowResult:
            import time
            t0 = time.monotonic()
            try:
                # 如果步骤依赖某些前置步骤的内存结果，先注入
                merged_task = dict(step.task)
                for dep_id in step.depends_on:
                    if dep_id in results and results[dep_id].response.ok:
                        merged_task.setdefault("_dep_results", {})
                        if isinstance(merged_task.get("_dep_results"), dict):
                            merged_task["_dep_results"][dep_id] = \
                                results[dep_id].response.data

                response = await asyncio.wait_for(
                    asyncio.to_thread(self._runtime.run_agent,
                                      self._kernel.get_agent(step.agent_id)
                                      or AgentInstance(agent_id=step.agent_id,
                                                       spec=AgentSpec(agent_id=step.agent_id,
                                                                      name="",
                                                                      engine="")),
                                      merged_task),
                    timeout=timeout_seconds,
                )
                elapsed = time.monotonic() - t0
                return WorkflowResult(step_id=step.step_id, agent_id=step.agent_id,
                                      response=response, elapsed_seconds=elapsed)
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t0
                return WorkflowResult(step_id=step.step_id, agent_id=step.agent_id,
                                      response=Response(ok=False, error="timeout"),
                                      elapsed_seconds=elapsed)
            except Exception as e:
                elapsed = time.monotonic() - t0
                return WorkflowResult(step_id=step.step_id, agent_id=step.agent_id,
                                      response=Response(ok=False, error=str(e)),
                                      elapsed_seconds=elapsed)

        # 分离出有依赖和无依赖的步骤
        independent = [s for s in pending if not s.depends_on]
        dependent = [s for s in pending if s.depends_on]

        if independent:
            batch_results = await asyncio.gather(
                *(_execute_one(s) for s in independent), return_exceptions=False
            )
            for wr in batch_results:
                if isinstance(wr, WorkflowResult):
                    results[wr.step_id] = wr

        # 处理有依赖的步骤：依赖全完成则执行
        for step in dependent:
            # 等待依赖（简单版：依赖都在 independent 中已并行完成）
            if all(dep in results for dep in step.depends_on):
                wr = await _execute_one(step)
                results[wr.step_id] = wr
            else:
                results[step.step_id] = WorkflowResult(
                    step_id=step.step_id, agent_id=step.agent_id,
                    response=Response(ok=False, error="unmet dependency"),
                    elapsed_seconds=0.0,
                )

        return list(results.values())

    # ── 引擎状态 ──
    def engine_health(self) -> str:
        return self._runtime.get_status("_engine")
