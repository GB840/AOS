"""SLA monitoring module.

Tracks API request latencies, status codes, and endpoints to compute
availability and latency percentiles. Supports hourly/daily/monthly
aggregation windows and detects anomalies (latency spikes, availability drops).
Thread-safe; stdlib only.
"""

from __future__ import annotations

import json
import math
import statistics
import threading
import time
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_AVAILABILITY_THRESHOLD = 99.9  # percent
_DEFAULT_P95_THRESHOLD_MS = 500.0
_ANOMALY_Z_SCORE = 3.0  # number of stddevs above mean to flag a spike
_DATA_DIR = Path(__file__).resolve().parent.parent / "_traces"
_SLA_FILE = _DATA_DIR / "sla_state.json"

# ---------------------------------------------------------------------------
# Enums / Data classes
# ---------------------------------------------------------------------------


class AggregationWindow(Enum):
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


@dataclass
class RequestRecord:
    timestamp: float
    endpoint: str
    status_code: int
    latency_ms: float


@dataclass
class SLAReport:
    period: str
    availability: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    total_requests: int
    failed_requests: int
    breaches: int


# ---------------------------------------------------------------------------
# SLA Monitor
# ---------------------------------------------------------------------------


class SLAMonitor:
    """Thread-safe SLA monitor that records requests and produces reports."""

    def __init__(
        self,
        availability_threshold: float = _DEFAULT_AVAILABILITY_THRESHOLD,
        p95_threshold_ms: float = _DEFAULT_P95_THRESHOLD_MS,
    ) -> None:
        self._lock = threading.Lock()
        self._records: list[RequestRecord] = []
        self._availability_threshold = availability_threshold
        self._p95_threshold_ms = p95_threshold_ms

    # -- recording -----------------------------------------------------------

    def record_request(
        self,
        endpoint: str,
        status_code: int,
        latency_ms: float,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a single API request.  timestamp defaults to now."""
        rec = RequestRecord(
            timestamp=timestamp or time.time(),
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=latency_ms,
        )
        with self._lock:
            self._records.append(rec)

    # -- filtering -----------------------------------------------------------

    def _records_in_window(
        self, window: AggregationWindow, reference_ts: Optional[float] = None
    ) -> list[RequestRecord]:
        """Return records whose timestamp falls inside the aggregation window."""
        ref = reference_ts or time.time()
        if window == AggregationWindow.HOUR:
            cutoff = ref - 3600
        elif window == AggregationWindow.DAY:
            cutoff = ref - 86400
        else:  # MONTH -- treat as 30 days
            cutoff = ref - 30 * 86400
        return [r for r in self._records if r.timestamp >= cutoff]

    # -- statistics ----------------------------------------------------------

    @staticmethod
    def _percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        k = (len(data) - 1) * pct / 100.0
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return data[int(k)]
        return data[f] * (c - k) + data[c] * (k - f)

    def _compute_anomalies(
        self, records: list[RequestRecord]
    ) -> list[dict]:
        """Detect latency spikes via z-score and availability breaches."""
        alerts: list[dict] = []
        if len(records) < 10:
            return alerts

        latencies = sorted(r.latency_ms for r in records)
        mean = statistics.mean(latencies)
        stdev = statistics.pstdev(latencies)
        if stdev == 0:
            return alerts

        threshold = mean + _ANOMALY_Z_SCORE * stdev
        spike_count = sum(1 for l in latencies if l > threshold)
        if spike_count:
            alerts.append(
                {
                    "type": "latency_spike",
                    "message": (
                        f"{spike_count} requests exceeded z-score threshold "
                        f"({threshold:.1f}ms, mean={mean:.1f}, stdev={stdev:.1f})"
                    ),
                }
            )

        # availability breach
        total = len(records)
        failed = sum(1 for r in records if r.status_code >= 500)
        avail = (total - failed) / total * 100 if total else 0
        if avail < self._availability_threshold:
            alerts.append(
                {
                    "type": "availability_breach",
                    "message": (
                        f"Availability {avail:.2f}% below threshold "
                        f"{self._availability_threshold}%"
                    ),
                }
            )

        return alerts

    # -- reporting -----------------------------------------------------------

    def get_sla_report(
        self,
        window: AggregationWindow = AggregationWindow.DAY,
        reference_ts: Optional[float] = None,
    ) -> SLAReport:
        """Return a structured SLA report for the given aggregation window."""
        records = self._records_in_window(window, reference_ts)
        total = len(records)
        failed = sum(1 for r in records if r.status_code >= 500)
        avail = (total - failed) / total * 100 if total else 0.0

        latencies = sorted(r.latency_ms for r in records)
        avg_lat = statistics.mean(latencies) if latencies else 0.0
        p95 = self._percentile(latencies, 95)
        p99 = self._percentile(latencies, 99)

        breaches = 0
        if avail < self._availability_threshold:
            breaches += 1
        if p95 > self._p95_threshold_ms:
            breaches += 1

        return SLAReport(
            period=window.value,
            availability=round(avail, 4),
            avg_latency_ms=round(avg_lat, 2),
            p95_latency_ms=round(p95, 2),
            p99_latency_ms=round(p99, 2),
            total_requests=total,
            failed_requests=failed,
            breaches=breaches,
        )

    def get_anomalies(
        self,
        window: AggregationWindow = AggregationWindow.DAY,
        reference_ts: Optional[float] = None,
    ) -> list[dict]:
        """Return detected anomalies for the given window."""
        records = self._records_in_window(window, reference_ts)
        return self._compute_anomalies(records)

    # -- persistence ---------------------------------------------------------

    def save(self, path: Optional[Path] = None) -> None:
        """Persist monitor state to disk (JSON)."""
        target = path or _SLA_FILE
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                "availability_threshold": self._availability_threshold,
                "p95_threshold_ms": self._p95_threshold_ms,
                "records": [
                    {
                        "ts": r.timestamp,
                        "ep": r.endpoint,
                        "sc": r.status_code,
                        "lat": r.latency_ms,
                    }
                    for r in self._records
                ],
            }
        target.write_text(json.dumps(data), encoding="utf-8")

    def load(self, path: Optional[Path] = None) -> None:
        """Load previously persisted state."""
        target = path or _SLA_FILE
        if not target.exists():
            return
        data = json.loads(target.read_text(encoding="utf-8"))
        with self._lock:
            self._availability_threshold = data.get(
                "availability_threshold", self._availability_threshold
            )
            self._p95_threshold_ms = data.get(
                "p95_threshold_ms", self._p95_threshold_ms
            )
            self._records = [
                RequestRecord(
                    timestamp=item["ts"],
                    endpoint=item["ep"],
                    status_code=item["sc"],
                    latency_ms=item["lat"],
                )
                for item in data.get("records", [])
            ]


# ---------------------------------------------------------------------------
# Module-level singleton + convenience functions
# ---------------------------------------------------------------------------

_monitor: Optional[SLAMonitor] = None
_monitor_lock = threading.Lock()


def _get_monitor() -> SLAMonitor:
    global _monitor
    if _monitor is None:
        with _monitor_lock:
            if _monitor is None:
                _monitor = SLAMonitor()
    return _monitor


def record_request(
    endpoint: str,
    status_code: int,
    latency_ms: float,
    timestamp: Optional[float] = None,
) -> None:
    """Record a single API request to the global SLA monitor."""
    _get_monitor().record_request(endpoint, status_code, latency_ms, timestamp)


def get_sla_report(
    window: AggregationWindow = AggregationWindow.DAY,
) -> SLAReport:
    """Return the current SLA report for the global monitor."""
    return _get_monitor().get_sla_report(window)


def get_anomalies(
    window: AggregationWindow = AggregationWindow.DAY,
) -> list[dict]:
    """Return detected anomalies from the global monitor."""
    return _get_monitor().get_anomalies(window)
