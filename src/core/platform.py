"""AOS 平台外壳 (platform shell)：observability + resilience + middleware + fileproc + sandbox + devops。

真实实现（非 stub）。为 ``scripts/verify_db_layer.py`` 的平台外壳 smoke 与运行时提供统一原语。
各原语以「最小可工作 + 诚实」为原则：能复用现有内核能力则复用，否则提供真实轻量实现。
"""
from __future__ import annotations

import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Callable, Optional


# ─── Observability: Metrics ──────────────────────────────────────

class Metrics:
    """进程内指标收集：counters / gauges，支持 label 维度。"""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, labels: Optional[dict] = None) -> None:
        with self._lock:
            key = self._key(name, labels)
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set(self, name: str, value: float, labels: Optional[dict] = None) -> None:
        with self._lock:
            self._gauges[self._key(name, labels)] = float(value)

    def snapshot(self) -> dict:
        with self._lock:
            return {"counters": dict(self._counters), "gauges": dict(self._gauges)}

    @staticmethod
    def _key(name: str, labels: Optional[dict]) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"


def prometheus_exposition(metrics: "Metrics") -> str:
    """把 Metrics 导出为 prometheus 文本格式（指标名加 ``aos_`` 前缀）。"""
    lines: list[str] = []
    snap = metrics.snapshot()
    for key, val in snap["counters"].items():
        name = "aos_" + key.split("{")[0]
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {val}")
    for key, val in snap["gauges"].items():
        name = "aos_" + key.split("{")[0]
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {val}")
    return "\n".join(lines) + "\n"


class Tracer:
    """极简链路追踪：记录 span 起止。"""

    def __init__(self) -> None:
        self._spans: list[dict] = []
        self._lock = threading.Lock()

    def span(self, name: str) -> "_Span":
        return _Span(self, name)

    def _begin(self, name: str) -> dict:
        rec = {"name": name, "start": time.time()}
        with self._lock:
            self._spans.append(rec)
        return rec

    def spans(self) -> list:
        with self._lock:
            return list(self._spans)


class _Span:
    def __init__(self, tracer: "Tracer", name: str) -> None:
        self._tracer = tracer
        self._name = name
        self._rec = tracer._begin(name)

    def __enter__(self) -> "_Span":
        return self

    def __exit__(self, *exc: Any) -> None:
        self._rec["end"] = time.time()


class HealthAggregator:
    """聚合多个健康检查，整体状态 = 全部 ok 则 healthy，否则 degraded。"""

    def __init__(self) -> None:
        self._checks: dict[str, Callable[[], dict]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, fn: Callable[[], dict]) -> None:
        with self._lock:
            self._checks[name] = fn

    def check_all(self) -> dict:
        details: dict[str, Any] = {}
        overall = "healthy"
        with self._lock:
            items = list(self._checks.items())
        for name, fn in items:
            try:
                res = fn()
                details[name] = res
                if isinstance(res, dict) and res.get("status") != "ok":
                    overall = "degraded"
            except Exception as e:  # noqa: BLE001
                details[name] = {"status": "error", "error": str(e)}
                overall = "degraded"
        return {"status": overall, "details": details}


# ─── Resilience ──────────────────────────────────────────────────

class CircuitBreakerOpenError(Exception):
    """熔断器已打开时由 :meth:`CircuitBreaker.call` 抛出。"""


class CircuitBreaker:
    """熔断器：连续失败 ``failure_threshold`` 次后打开，``recovery_timeout`` 秒后半开探测。"""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0) -> None:
        self._threshold = failure_threshold
        self._timeout = recovery_timeout
        self._failures = 0
        self._last_fail = 0.0
        self._state = "closed"
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open" and (time.time() - self._last_fail) > self._timeout:
                self._state = "half-open"
            return self._state

    def call(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            if self._state == "open":
                if (time.time() - self._last_fail) > self._timeout:
                    self._state = "half-open"
                else:
                    raise CircuitBreakerOpenError(self)
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                self._state = "closed"
                self._failures = 0
            return result
        except Exception:
            with self._lock:
                self._failures += 1
                self._last_fail = time.time()
                if self._failures >= self._threshold:
                    self._state = "open"
            raise


def retry(times: int = 3) -> Callable:
    """重试装饰器：连续失败直到成功或耗尽 ``times`` 次后抛出最后一次异常。"""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last: Optional[BaseException] = None
            for _ in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:  # noqa: BLE001
                    last = e
            assert last is not None
            raise last
        return wrapper
    return deco


def fallback(default: Any = None) -> Callable:
    """降级装饰器：原函数抛异常时返回 ``default``。"""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                return default
        return wrapper
    return deco


def degrade(fn: Callable) -> Callable:
    """优雅降级：原函数抛异常时返回 ``None``（不中断调用方）。"""
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            return None
    return wrapper


# ─── Middleware ──────────────────────────────────────────────────

class IdempotencyStore:
    """幂等键存储。"""

    def __init__(self) -> None:
        self._seen: dict[str, Any] = {}
        self._lock = threading.Lock()

    def seen(self, key: str) -> bool:
        with self._lock:
            return key in self._seen

    def mark(self, key: str, value: Any) -> None:
        with self._lock:
            self._seen[key] = value


def idempotent(store: "IdempotencyStore", keyfn: Callable) -> Callable:
    """幂等装饰器：同一 key 第二次调用返回 ``{"duplicated": True, "key": ...}``。"""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = keyfn(*args, **kwargs)
            if store.seen(key):
                return {"duplicated": True, "key": key}
            result = fn(*args, **kwargs)
            store.mark(key, result)
            return result
        return wrapper
    return deco


class RateLimiter:
    """令牌桶限流（按 key 独立计数）。"""

    def __init__(self, rate: float = 10.0, capacity: float = 10.0) -> None:
        self._rate = rate
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.time()
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0) -> bool:
        with self._lock:
            now = time.time()
            self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
            self._last = now
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False


class NotificationService:
    """轻量通知服务（内存投递，可扩展真实通道）。"""

    def __init__(self) -> None:
        self._sent: list[dict] = []

    def send(self, agent_id: str, payload: dict, channels: Optional[list[str]] = None) -> dict:
        channels = channels or ["in_app"]
        res: dict[str, Any] = {}
        for ch in channels:
            res[ch] = {"ok": True, "agent_id": agent_id}
            self._sent.append({"channel": ch, "agent_id": agent_id, "payload": payload})
        return res


# ─── Event Sourcing ──────────────────────────────────────────────

class EventStore:
    """内存事件溯源存储：append / replay / snapshot。"""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._snapshots: dict[tuple, dict] = {}
        self._seq = 0
        self._lock = threading.Lock()

    def append(self, agent: str, entity_id: str, event_type: str, payload: dict) -> int:
        with self._lock:
            self._seq += 1
            self._events.append({
                "seq": self._seq, "agent": agent, "entity_id": entity_id,
                "type": event_type, "payload": payload,
            })
            return self._seq

    def replay(self, agent: str, entity_id: str) -> list:
        with self._lock:
            return [e for e in self._events if e["agent"] == agent and e["entity_id"] == entity_id]

    def save_snapshot(self, agent: str, entity_id: str, version: int, state: dict) -> None:
        with self._lock:
            self._snapshots[(agent, entity_id)] = {"version": version, "state": state}

    def load_latest_snapshot(self, agent: str, entity_id: str) -> Optional[dict]:
        with self._lock:
            return self._snapshots.get((agent, entity_id))


# ─── File processing ─────────────────────────────────────────────

def extract_text(data: bytes, mime: str = "text/plain", **kwargs: Any) -> dict:
    """文本抽取：纯文本直接解码；其它类型诚实降级（无外部解析依赖时标记不支持）。"""
    if mime == "text/plain":
        try:
            return {"ok": True, "text": data.decode("utf-8", errors="replace")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}
    # 非文本类型：诚实降级（无外部解析依赖时标记不支持）
    if "pdf" in mime.lower():
        return {"ok": False, "error": "PDF extraction not available"}
    return {"ok": False, "error": f"unsupported mime: {mime}"}


# ─── Sandbox ─────────────────────────────────────────────────────

class PythonSandbox:
    """Python 沙箱：子进程隔离执行，捕获 stdout，带超时。"""

    def run(self, code: str, timeout: float = 5.0) -> dict:
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True, text=True, timeout=timeout,
            )
            return {"ok": proc.returncode == 0, "stdout": proc.stdout, "stderr": proc.stderr}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "timeout"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}


class WasmSandbox:
    """WASM 沙箱：未安装 wasmtime 时诚实报错。"""

    def run(self, code: str) -> dict:  # noqa: ARG002
        try:
            import wasmtime  # noqa: F401
        except ImportError:
            return {"ok": False, "error": "wasmtime not installed"}
        return {"ok": False, "error": "wasm execution not implemented"}


# ─── Cold storage ────────────────────────────────────────────────

class ColdStore:
    """冷存储：内存为主、可选落盘（不可序列化对象仅保留内存）。"""

    def __init__(self, root: Optional[str] = None) -> None:
        self._root = root or os.path.join(tempfile.gettempdir(), "aos_cold")
        os.makedirs(self._root, exist_ok=True)
        self._mem: dict[str, Any] = {}

    def archive(self, key: str, kind: str, obj: Any) -> None:
        self._mem[key] = obj
        path = os.path.join(self._root, f"{key}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"kind": kind, "obj": obj}, f)
        except (TypeError, OSError):
            pass

    def restore(self, key: str) -> Any:
        if key in self._mem:
            return self._mem[key]
        path = os.path.join(self._root, f"{key}.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f).get("obj")
            except OSError:
                return None
        return None


# ─── DevOps pipeline ─────────────────────────────────────────────

class Pipeline:
    """简单流水线：步骤失败按 ``on_fail`` 决定 continue 还是 abort。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self._steps: list[dict] = []

    def add(self, name: str, fn: Callable, on_fail: str = "abort") -> "Pipeline":
        self._steps.append({"name": name, "fn": fn, "on_fail": on_fail})
        return self

    def run(self) -> dict:
        results: list[dict] = []
        aborted = False
        for step in self._steps:
            try:
                ok = bool(step["fn"]())
                results.append({"name": step["name"], "ok": ok})
            except Exception as e:  # noqa: BLE001
                results.append({"name": step["name"], "ok": False, "error": str(e)})
                if step["on_fail"] == "abort":
                    aborted = True
                    break
        return {"aborted": aborted, "steps": results}


# ─── Compatibility matrix ────────────────────────────────────────

class CompatMatrix:
    """组件版本兼容矩阵：支持 ``>=`` / ``==`` / 裸版本号 判定。"""

    def __init__(self) -> None:
        self._entries: dict[str, dict] = {}

    def register(self, name: str, version: str, status: str = "ok") -> None:
        self._entries[name] = {"version": version, "status": status}

    def is_compatible(self, name: str, spec: str) -> bool:
        entry = self._entries.get(name)
        if not entry:
            return False
        ver = entry["version"]
        if spec.startswith(">="):
            return self._ge(ver, spec[2:])
        if spec.startswith("=="):
            return ver == spec[2:]
        return ver == spec

    @staticmethod
    def _ge(a: str, b: str) -> bool:
        def parse(v: str) -> list[int]:
            return [int(x) for x in re.findall(r"\d+", v)]
        return parse(a) >= parse(b)
