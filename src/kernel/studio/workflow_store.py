"""工作流存储 —— Studio 工作流的持久化管理。

支持：CRUD、版本管理、搜索、模板市场、分类。

设计原则：
- 本地文件存储（JSON），零依赖，开箱即用
- 每个工作流一个目录，存所有版本
- 索引文件加速搜索和列表
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from .workflow_models import Workflow, WorkflowRun

logger = __import__("logging").getLogger(__name__)

_WORKFLOW_DIR = os.environ.get(
    "AOS_WORKFLOW_DIR",
    os.path.join("data", "workspaces", "fabric", "workflows"),
)


def _wf_dir() -> str:
    os.makedirs(_WORKFLOW_DIR, exist_ok=True)
    return _WORKFLOW_DIR


def _wf_path(wf_id: str) -> str:
    return os.path.join(_wf_dir(), wf_id)


def _index_path() -> str:
    return os.path.join(_wf_dir(), "_index.json")


class WorkflowStore:
    """工作流存储。

    目录结构：
        workflows/
            _index.json          # 索引（所有工作流的摘要）
            {wf_id}/
                workflow.json   # 当前版本
                versions/
                    v1.0.0.json
                    v1.1.0.json
                runs/
                    {run_id}.json
    """

    def __init__(self, base_dir: str = None):
        self._base_dir = base_dir or _wf_dir()
        os.makedirs(self._base_dir, exist_ok=True)
        self._index_path = os.path.join(self._base_dir, "_index.json")
        self._index = self._load_index()

    # ── 索引管理 ──

    def _load_index(self) -> Dict[str, Any]:
        if os.path.exists(self._index_path):
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"workflows": [], "templates": []}

    def _save_index(self) -> None:
        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存工作流索引失败: %s", e)

    def _update_index(self, wf: Workflow) -> None:
        item = {
            "id": wf.id,
            "name": wf.name,
            "description": wf.description,
            "category": wf.category,
            "tags": wf.tags,
            "author": wf.author,
            "version": wf.version,
            "step_count": len(wf.steps),
            "updated_at": wf.updated_at,
            "run_count": wf.run_count,
            "success_rate": wf.success_rate,
            "is_template": wf.is_template,
            "is_public": wf.is_public,
        }

        # 更新列表
        workflows = self._index.get("workflows", [])
        found = False
        for i, w in enumerate(workflows):
            if w["id"] == wf.id:
                workflows[i] = item
                found = True
                break
        if not found:
            workflows.append(item)
        self._index["workflows"] = workflows

        # 更新模板列表
        templates = self._index.get("templates", [])
        if wf.is_template:
            found = False
            for i, t in enumerate(templates):
                if t["id"] == wf.id:
                    templates[i] = item
                    found = True
                    break
            if not found:
                templates.append(item)
        else:
            templates = [t for t in templates if t["id"] != wf.id]
        self._index["templates"] = templates

        self._save_index()

    # ── CRUD ──

    def create(self, name: str, description: str = "", author: str = "user") -> Workflow:
        """创建新工作流。"""
        wf = Workflow.create(name=name, description=description, author=author)
        self._save_workflow_file(wf)
        self._update_index(wf)
        return wf

    def get(self, wf_id: str) -> Optional[Workflow]:
        """获取工作流。"""
        wf_dir = os.path.join(self._base_dir, wf_id, "workflow.json")
        if not os.path.exists(wf_dir):
            return None
        try:
            with open(wf_dir, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Workflow.from_dict(data)
        except Exception as e:
            logger.warning("加载工作流 %s 失败: %s", wf_id, e)
            return None

    def save(self, wf: Workflow, *, new_version: bool = False) -> Workflow:
        """保存工作流。

        new_version=True 时保存为新版本，不覆盖旧版本。
        """
        if new_version:
            # 保存旧版本
            self._save_version(wf)
            # 版本号 +0.1
            parts = wf.version.split(".")
            parts[-1] = str(int(parts[-1]) + 1 if parts[-1].isdigit() else "1")
            wf.version = ".".join(parts)

        wf._touch()
        self._save_workflow_file(wf)
        self._update_index(wf)
        return wf

    def delete(self, wf_id: str) -> bool:
        """删除工作流。"""
        wf_dir = os.path.join(self._base_dir, wf_id)
        if not os.path.exists(wf_dir):
            return False
        try:
            shutil.rmtree(wf_dir)
            # 更新索引
            self._index["workflows"] = [
                w for w in self._index.get("workflows", []) if w["id"] != wf_id
            ]
            self._index["templates"] = [
                t for t in self._index.get("templates", []) if t["id"] != wf_id
            ]
            self._save_index()
            return True
        except Exception as e:
            logger.warning("删除工作流 %s 失败: %s", wf_id, e)
            return False

    def list(self, *, category: str = "", tag: str = "", is_template: bool = None,
             author: str = "", search: str = "", limit: int = 50, offset: int = 0
             ) -> List[Dict[str, Any]]:
        """列出工作流。"""
        items = self._index.get("workflows", [])

        if category:
            items = [i for i in items if i.get("category") == category]
        if tag:
            items = [i for i in items if tag in i.get("tags", [])]
        if is_template is not None:
            items = [i for i in items if i.get("is_template") == is_template]
        if author:
            items = [i for i in items if i.get("author") == author]
        if search:
            search_lower = search.lower()
            items = [
                i for i in items
                if search_lower in i.get("name", "").lower()
                or search_lower in i.get("description", "").lower()
            ]

        # 按更新时间倒序
        items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)

        return items[offset:offset + limit]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索工作流。"""
        return self.list(search=query, limit=limit)

    # ── 版本管理 ──

    def list_versions(self, wf_id: str) -> List[str]:
        """列出所有版本。"""
        versions_dir = os.path.join(self._base_dir, wf_id, "versions")
        if not os.path.exists(versions_dir):
            return []
        try:
            files = os.listdir(versions_dir)
            return sorted([f.replace(".json", "") for f in files if f.endswith(".json")])
        except Exception:
            return []

    def get_version(self, wf_id: str, version: str) -> Optional[Workflow]:
        """获取指定版本。"""
        v_path = os.path.join(self._base_dir, wf_id, "versions", f"{version}.json")
        if not os.path.exists(v_path):
            return None
        try:
            with open(v_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Workflow.from_dict(data)
        except Exception:
            return None

    def revert_to_version(self, wf_id: str, version: str) -> Optional[Workflow]:
        """回退到指定版本。"""
        old_wf = self.get_version(wf_id, version)
        if not old_wf:
            return None
        # 保存当前版本
        current = self.get(wf_id)
        if current:
            self._save_version(current)
        # 用旧版本覆盖当前
        old_wf._touch()
        self._save_workflow_file(old_wf)
        self._update_index(old_wf)
        return old_wf

    # ── 运行记录 ──

    def save_run(self, run: WorkflowRun) -> None:
        """保存运行记录。"""
        runs_dir = os.path.join(self._base_dir, run.workflow_id, "runs")
        os.makedirs(runs_dir, exist_ok=True)
        run_path = os.path.join(runs_dir, f"{run.id}.json")
        try:
            with open(run_path, "w", encoding="utf-8") as f:
                json.dump(asdict(run), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("保存运行记录失败: %s", e)

    def list_runs(self, wf_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """列出运行记录（按 mtime 倒序，取最近 limit 条）。

        修复 P1-8：原为 sorted(os.listdir(...), reverse=True) 按文件名(uuid)
        字母序排序——uuid 无时间序，返回的不是「最近 N 条」。改为按 mtime
        排序，与「最近运行」语义对齐。
        """
        runs_dir = os.path.join(self._base_dir, wf_id, "runs")
        if not os.path.exists(runs_dir):
            return []
        try:
            files = sorted(
                os.listdir(runs_dir),
                key=lambda f: os.path.getmtime(os.path.join(runs_dir, f)),
                reverse=True,
            )
            runs = []
            for f in files[:limit]:
                if f.endswith(".json"):
                    try:
                        with open(os.path.join(runs_dir, f), "r", encoding="utf-8") as fp:
                            runs.append(json.load(fp))
                    except Exception:
                        pass
            return runs
        except Exception:
            return []

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """按 run_id 取一条运行记录（用于回放调试 / what-if 分析）。

        扫描所有工作流的 runs 目录；run_id 全局唯一（uuid），命中即返回。
        """
        try:
            base = self._base_dir
            for wf_id in os.listdir(base):
                runs_dir = os.path.join(base, wf_id, "runs")
                if not os.path.isdir(runs_dir):
                    continue
                path = os.path.join(runs_dir, f"{run_id}.json")
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as fp:
                        return json.load(fp)
        except Exception:
            return None
        return None

    def list_traces(self, *, wf_id: str = "", limit: int = 50,
                    status: str = "") -> List[Dict[str, Any]]:
        """跨工作流列出运行记录（Task 5: Replay & Debug 用）。

        扫描所有 workflows/*/runs/*.json，按 started_at 倒序返回摘要。
        摘要字段：run_id / workflow_id / status / started_at / duration / step_count
        （不含 steps 详细内容，避免大负载）

        Args:
            wf_id: 仅列出该工作流的运行（空=全部）
            limit: 最多返回多少条
            status: 仅返回该状态（success/failed/partial/running/awaiting_approval）
        """
        traces: List[Dict[str, Any]] = []
        try:
            base = self._base_dir
            wf_ids = [wf_id] if wf_id else os.listdir(base)
            for wid in wf_ids:
                runs_dir = os.path.join(base, wid, "runs")
                if not os.path.isdir(runs_dir):
                    continue
                for fname in os.listdir(runs_dir):
                    if not fname.endswith(".json"):
                        continue
                    path = os.path.join(runs_dir, fname)
                    try:
                        with open(path, "r", encoding="utf-8") as fp:
                            data = json.load(fp)
                    except Exception:
                        continue
                    if status and data.get("status") != status:
                        continue
                    steps = data.get("steps") or []
                    traces.append({
                        "run_id": data.get("id", fname[:-5]),
                        "workflow_id": data.get("workflow_id", wid),
                        "status": data.get("status", ""),
                        "started_at": data.get("started_at", ""),
                        "ended_at": data.get("ended_at", ""),
                        "duration": data.get("duration", 0.0),
                        "step_count": len(steps),
                        "ok_steps": sum(1 for s in steps if s.get("ok")),
                        "error": data.get("error", ""),
                    })
        except Exception as e:
            logger.warning("list_traces 失败: %s", e)
            return []

        # 按 started_at 倒序（最近的在前）
        traces.sort(key=lambda x: x.get("started_at", ""), reverse=True)
        return traces[:limit]

    # ── 内部方法 ──

    def _save_workflow_file(self, wf: Workflow) -> None:
        wf_dir = os.path.join(self._base_dir, wf.id)
        os.makedirs(wf_dir, exist_ok=True)
        os.makedirs(os.path.join(wf_dir, "versions"), exist_ok=True)
        os.makedirs(os.path.join(wf_dir, "runs"), exist_ok=True)

        wf_path = os.path.join(wf_dir, "workflow.json")
        with open(wf_path, "w", encoding="utf-8") as f:
            json.dump(wf.to_dict(), f, ensure_ascii=False, indent=2)

    def _save_version(self, wf: Workflow) -> None:
        versions_dir = os.path.join(self._base_dir, wf.id, "versions")
        os.makedirs(versions_dir, exist_ok=True)
        v_path = os.path.join(versions_dir, f"{wf.version}.json")
        with open(v_path, "w", encoding="utf-8") as f:
            json.dump(wf.to_dict(), f, ensure_ascii=False, indent=2)


# 单例
_store: Optional[WorkflowStore] = None


def get_workflow_store() -> WorkflowStore:
    global _store
    if _store is None:
        _store = WorkflowStore()
    return _store
