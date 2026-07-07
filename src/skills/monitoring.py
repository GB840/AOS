from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import logging
from pathlib import Path
import time

logger = logging.getLogger(__name__)

class SkillMetric:
    def __init__(self, name: str, value: float, unit: str = "", tags: Optional[Dict[str, str]] = None):
        self.name = name
        self.value = value
        self.unit = unit
        self.tags = tags or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "tags": self.tags,
            "timestamp": self.timestamp,
        }

class SkillSpan:
    def __init__(self, name: str, skill_name: str):
        self.name = name
        self.skill_name = skill_name
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: Optional[float] = None
        self.status = "running"
        self.attributes: Dict[str, Any] = {}
        self.events: List[Dict[str, Any]] = []
    
    def end(self, status: str = "success", error: Optional[str] = None):
        self.end_time = time.time()
        self.duration_ms = (self.end_time - self.start_time) * 1000
        self.status = status
        if error:
            self.attributes["error"] = error
    
    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        self.events.append({
            "name": name,
            "timestamp": datetime.now().isoformat(),
            "attributes": attributes or {},
        })
    
    def set_attribute(self, key: str, value: Any):
        self.attributes[key] = value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "skill_name": self.skill_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }

class SkillMonitor:
    def __init__(self, storage_path: str = "outputs/skills/monitoring"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.spans: List[SkillSpan] = []
        self.metrics: List[SkillMetric] = []
        self.active_spans: Dict[str, SkillSpan] = {}
        self._load_data()
    
    def _load_data(self):
        metrics_file = self.storage_path / "metrics.json"
        
        if metrics_file.exists():
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.metrics = [SkillMetric(**item) for item in data]
            except:
                pass
    
    def _save_data(self):
        metrics_file = self.storage_path / "metrics.json"
        
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump([m.to_dict() for m in self.metrics], f, ensure_ascii=False, indent=2)
    
    def start_span(self, name: str, skill_name: str) -> str:
        span_id = f"{skill_name}_{int(time.time() * 1000)}_{len(self.active_spans)}"
        span = SkillSpan(name, skill_name)
        self.active_spans[span_id] = span
        return span_id
    
    def end_span(self, span_id: str, status: str = "success", error: Optional[str] = None):
        if span_id in self.active_spans:
            span = self.active_spans[span_id]
            span.end(status, error)
            self.spans.append(span)
            del self.active_spans[span_id]
            
            if len(self.spans) > 5000:
                self.spans = self.spans[-2000:]
            
            self.record_metric("skill.execution.duration", span.duration_ms, "ms", {"skill_name": span.skill_name})
            self.record_metric("skill.execution.count", 1, "count", {"skill_name": span.skill_name, "status": status})
    
    def add_event_to_span(self, span_id: str, name: str, attributes: Optional[Dict[str, Any]] = None):
        if span_id in self.active_spans:
            self.active_spans[span_id].add_event(name, attributes)
    
    def set_span_attribute(self, span_id: str, key: str, value: Any):
        if span_id in self.active_spans:
            self.active_spans[span_id].set_attribute(key, value)
    
    def record_metric(self, name: str, value: float, unit: str = "", tags: Optional[Dict[str, str]] = None):
        metric = SkillMetric(name, value, unit, tags)
        self.metrics.append(metric)
        
        if len(self.metrics) > 10000:
            self.metrics = self.metrics[-5000:]
        
        self._save_data()
    
    def record_skill_execution(self, skill_name: str, context: Dict[str, Any], result: Dict[str, Any], duration_ms: float):
        status = "success" if result.get("success", True) else "error"
        
        span_id = self.start_span(f"{skill_name}.execute", skill_name)
        self.set_span_attribute(span_id, "context", str(context)[:500])
        self.set_span_attribute(span_id, "result", str(result)[:500])
        
        if "error" in result:
            self.add_event_to_span(span_id, "error", {"message": result["error"]})
        
        self.end_span(span_id, status, result.get("error"))
        
        self.record_metric("skill.execution.duration", duration_ms, "ms", {"skill_name": skill_name})
        self.record_metric("skill.execution.count", 1, "count", {"skill_name": skill_name, "status": status})
        
        if status == "error":
            self.record_metric("skill.execution.errors", 1, "count", {"skill_name": skill_name})
    
    def get_skill_metrics(self, skill_name: str) -> Dict[str, Any]:
        skill_metrics = [m for m in self.metrics if m.tags.get("skill_name") == skill_name]
        
        total_executions = sum(1 for m in skill_metrics if m.name == "skill.execution.count")
        successful_executions = sum(1 for m in skill_metrics if m.name == "skill.execution.count" and m.tags.get("status") == "success")
        error_count = sum(1 for m in skill_metrics if m.name == "skill.execution.errors")
        
        durations = [m.value for m in skill_metrics if m.name == "skill.execution.duration"]
        avg_duration = sum(durations) / max(len(durations), 1) if durations else 0
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        
        return {
            "skill_name": skill_name,
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "error_count": error_count,
            "success_rate": round(successful_executions / max(total_executions, 1), 2),
            "avg_duration_ms": round(avg_duration, 2),
            "max_duration_ms": round(max_duration, 2),
            "min_duration_ms": round(min_duration, 2),
        }
    
    def get_recent_spans(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [span.to_dict() for span in self.spans[-limit:]]
    
    def get_span_by_id(self, span_id: str) -> Optional[Dict[str, Any]]:
        for span in self.spans:
            if span_id in str(span.name) + str(span.skill_name):
                return span.to_dict()
        return None
    
    def get_overall_stats(self) -> Dict[str, Any]:
        skill_names = set(m.tags.get("skill_name") for m in self.metrics if m.tags.get("skill_name"))
        
        skill_stats = {}
        for skill_name in skill_names:
            skill_stats[skill_name] = self.get_skill_metrics(skill_name)
        
        total_span_count = len(self.spans)
        total_metric_count = len(self.metrics)
        
        success_count = sum(1 for m in self.metrics if m.name == "skill.execution.count" and m.tags.get("status") == "success")
        total_count = sum(1 for m in self.metrics if m.name == "skill.execution.count")
        overall_success_rate = round(success_count / max(total_count, 1), 2)
        
        return {
            "total_spans": total_span_count,
            "total_metrics": total_metric_count,
            "overall_success_rate": overall_success_rate,
            "skill_stats": skill_stats,
        }
    
    def export_metrics(self, format: str = "json") -> str:
        if format == "json":
            return json.dumps([m.to_dict() for m in self.metrics], ensure_ascii=False, indent=2)
        elif format == "prometheus":
            lines = []
            for metric in self.metrics:
                tags_str = ",".join(f'{k}="{v}"' for k, v in metric.tags.items())
                if tags_str:
                    tags_str = "{" + tags_str + "}"
                lines.append(f'skill_{metric.name.replace(".", "_")}{tags_str} {metric.value}')
            return "\n".join(lines)
        else:
            return json.dumps([m.to_dict() for m in self.metrics], ensure_ascii=False)
    
    def export_spans(self, format: str = "json") -> str:
        if format == "json":
            return json.dumps([s.to_dict() for s in self.spans], ensure_ascii=False, indent=2)
        elif format == "trace":
            traces = []
            for span in self.spans:
                trace = {
                    "traceId": span.name,
                    "spanId": f"{span.skill_name}_{int(span.start_time * 1000)}",
                    "name": span.name,
                    "serviceName": span.skill_name,
                    "startTime": span.start_time,
                    "duration": span.duration_ms,
                    "statusCode": "OK" if span.status == "success" else "ERROR",
                    "tags": span.attributes,
                }
                traces.append(trace)
            return json.dumps(traces, ensure_ascii=False, indent=2)
        else:
            return json.dumps([s.to_dict() for s in self.spans], ensure_ascii=False)

_default_monitor = None

def get_monitor() -> SkillMonitor:
    global _default_monitor
    if _default_monitor is None:
        _default_monitor = SkillMonitor()
    return _default_monitor