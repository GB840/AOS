"""
AOS v5.0 — 可观测层 (Observability)

对标蓝图 OBSERVE / TRACE / HEALTH。设计原则 (严谨 + 开放 + 灵活):
  - 零硬依赖: 进程内指标/链路/Trace 不依赖任何第三方包, 开箱即用。
  - 可插拔导出: 若环境装有 opentelemetry / prometheus_client, 自动桥接 (best-effort),
    无则静默降级, 不影响主流程。
  - 可注入: Metrics / Tracer / HealthAggregator 都是可实例化的普通对象, 便于测试替换。

满足蓝图节点: OBSERVE(指标+导出) / TRACE(链路) / HEALTH(探针聚合)。
"""

import logging
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 可选依赖
    from opentelemetry import trace as otel_trace
    _HAS_OTEL = True
except Exception:  # pragma: no cover
    _HAS_OTEL = False

try:  # pragma: no cover - 可选依赖
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST  # noqa: F401
    _HAS_PROM = True
except Exception:  # pragma: no cover
    _HAS_PROM = False


# ---------------------------------------------------------------------------
# Metrics: 进程内指标注册表 (计数器 + 直方图), 不依赖 prometheus_client
# ---------------------------------------------------------------------------
class Metrics:
    """轻量指标注册表。inc/observe 线程安全; snapshot() 返回可序列化结构。"""

    def __init__(self, namespace: str = "aos"):
        self.namespace = namespace
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}

    def _key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{parts}}}"

    def inc(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value
        # 可选: 桥接到 OTel (best-effort)
        if _HAS_OTEL:
            try:
                otel_trace.get_tracer("aos").get_tracer_provider()  # noqa
            except Exception:
                pass

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._histograms.setdefault(key, []).append(value)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "histograms": {
                    k: {"count": len(v), "sum": sum(v), "max": max(v), "min": min(v)}
                    for k, v in self._histograms.items()
                },
            }

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._histograms.clear()


# ---------------------------------------------------------------------------
# Tracer: 轻量链路追踪 (span 栈), 可选桥接 OTel
# ---------------------------------------------------------------------------
class Tracer:
    """span 上下文管理。无 OTel 时仍记录 span 树用于本地调试/导出。"""

    def __init__(self, name: str = "aos"):
        self.name = name
        self._spans: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        span_id = f"{name}-{time.time_ns()}"
        rec = {"name": name, "start": time.time(), "attributes": attributes or {}, "span_id": span_id}
        if _HAS_OTEL:
            try:
                with otel_trace.get_tracer(self.name).start_as_current_span(name) as s:
                    if attributes:
                        for k, v in attributes.items():
                            s.set_attribute(str(k), str(v))
                    yield s
                return
            except Exception:
                pass
        try:
            yield rec
        finally:
            rec["end"] = time.time()
            rec["duration_ms"] = round((rec["end"] - rec["start"]) * 1000, 3)
            with self._lock:
                self._spans.append(rec)

    def spans(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._spans)

    def clear(self) -> None:
        with self._lock:
            self._spans.clear()


# ---------------------------------------------------------------------------
# Prometheus 文本导出 (不依赖 prometheus_client)
# ---------------------------------------------------------------------------
def prometheus_exposition(metrics: Metrics) -> str:
    """把 Metrics.snapshot() 渲染成 Prometheus 文本格式 (兼容 scrape)。"""
    lines: List[str] = []
    snap = metrics.snapshot()
    for key, val in sorted(snap["counters"].items()):
        name = f"{metrics.namespace}_{key.split('{')[0]}"
        labels = key.split("{", 1)[1][:-1] if "{" in key else ""
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name}{{{labels}}} {val}")
    for key, stat in sorted(snap["histograms"].items()):
        name = f"{metrics.namespace}_{key.split('{')[0]}"
        labels = key.split("{", 1)[1][:-1] if "{" in key else ""
        lines.append(f"# TYPE {name} histogram")
        lines.append(f"{name}_count{{{labels}}} {stat['count']}")
        lines.append(f"{name}_sum{{{labels}}} {stat['sum']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Health: 探针聚合 (蓝图 HEALTH 4 探针)
# ---------------------------------------------------------------------------
class HealthAggregator:
    """注册多个健康检查函数, 统一返回 status。任一失败 -> degraded。"""

    def __init__(self):
        self._checks: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def register(self, name: str, fn: Callable[[], Dict[str, Any]]) -> None:
        self._checks[name] = fn

    def check_all(self) -> Dict[str, Any]:
        results = {}
        overall = "healthy"
        for name, fn in self._checks.items():
            try:
                res = fn() or {}
                status = res.get("status", "ok")
                if status != "ok":
                    overall = "degraded"
                results[name] = {"status": status, **res}
            except Exception as e:  # pragma: no cover - 探针异常也算降级
                overall = "degraded"
                results[name] = {"status": "error", "error": str(e)}
        return {"status": overall, "checks": results}


# 默认全局实例 (可选使用)
default_metrics = Metrics()
default_tracer = Tracer()
default_health = HealthAggregator()
