"""创业仪表盘API——提供创业状态总览、产出物检测、ROI计算。

路由前缀: /api/startup
"""
from __future__ import annotations
import os
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# 输出目录（autopilot/aos 的产出文件默认位置）
_OUTPUT_ROOTS = [
    os.path.join(os.path.dirname(__file__), "..", "..", "_output"),
    os.path.join(os.path.dirname(__file__), "..", "..", "_video_output"),
]


def scan_new_artifacts(before_snapshot: Dict[str, set] = None) -> List[Dict[str, Any]]:
    """扫描_output/_video_output目录新增文件。"""
    artifacts = []
    for root in _OUTPUT_ROOTS:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        try:
            current = set(os.listdir(root))
        except OSError:
            continue
        if before_snapshot and root in before_snapshot:
            current = current - before_snapshot[root]
        for name in sorted(current):
            fp = os.path.join(root, name)
            if os.path.isfile(fp):
                stat = os.stat(fp)
                artifacts.append({
                    "path": fp,
                    "name": name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": _file_type(name),
                })
    return artifacts


def _file_type(name: str) -> str:
    ext = os.path.splitext(name)[1].lower()
    type_map = {
        ".mp4": "video", ".avi": "video", ".mov": "video",
        ".mp3": "audio", ".wav": "audio",
        ".png": "image", ".jpg": "image", ".jpeg": "image",
        ".md": "document", ".txt": "document", ".pdf": "document",
        ".csv": "data", ".json": "data", ".xlsx": "data",
        ".py": "code", ".js": "code", ".html": "code",
    }
    return type_map.get(ext, "other")


def snapshot_output_dirs() -> Dict[str, set]:
    """快照输出目录现有文件。"""
    snap = {}
    for root in _OUTPUT_ROOTS:
        root = os.path.abspath(root)
        if os.path.isdir(root):
            try:
                snap[root] = set(os.listdir(root))
            except OSError:
                snap[root] = set()
    return snap


def compute_roi(tenant_id: str, startup_engine) -> Dict[str, Any]:
    """计算创业ROI（简化版）。"""
    status = startup_engine.get_status(tenant_id)
    if "error" in status:
        return {"error": status["error"]}
    progress = status.get("progress", {})
    completed = progress.get("completed", 0)
    total = progress.get("total", 1)
    completion_rate = completed / total if total > 0 else 0.0
    return {
        "tenant_id": tenant_id,
        "completion_rate": round(completion_rate * 100, 1),
        "tasks_completed": completed,
        "tasks_total": total,
        "estimated_monthly_value": round(completion_rate * 2000, 2),  # 简化估值
        "cost_estimate": round(total * 0.5, 2),  # 简化成本
        "roi_ratio": round(completion_rate * 2000 / max(total * 0.5, 0.01), 2),
    }


def get_dashboard(tenant_id: str, startup_engine) -> Dict[str, Any]:
    """创业仪表盘完整数据。"""
    status = startup_engine.get_status(tenant_id)
    roi = compute_roi(tenant_id, startup_engine)
    artifacts = scan_new_artifacts()
    return {
        "status": status,
        "roi": roi,
        "recent_artifacts": artifacts[:20],  # 最近20个产出文件
        "artifact_count": len(artifacts),
        "generated_at": datetime.now().isoformat(),
    }


# ── FastAPI 路由 ─────────────────────────────────────────────
from fastapi import APIRouter

router = APIRouter(prefix="/api/startup", tags=["startup"])


def _get_startup_engine():
    try:
        from kernel.danchuang.engine.startup_engine import StartupEngine
        return StartupEngine()
    except Exception:
        return None


@router.get("/dashboard/{tenant_id}")
def dashboard_api(tenant_id: str):
    engine = _get_startup_engine()
    if engine is None:
        return {"error": "StartupEngine不可用"}
    return get_dashboard(tenant_id, engine)


@router.get("/artifacts")
def artifacts_api():
    return {"artifacts": scan_new_artifacts()}


def mount_startup_api(app):
    app.include_router(router)