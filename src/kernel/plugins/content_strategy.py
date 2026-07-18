"""内容策略存储 —— 内容飞轮自动反哺的落地载体。

Evolve 基于 Echo 反馈生成 ``content_keyword_adjust``（low-risk）提案，
自动应用后写入本存储；内容生成阶段（content.marketing_video / Forge）可读取这里的
关键词权重，偏好强化正面关键词、降低负面话题 —— 这就是「双飞轮互相增强」的
内容侧闭环（产品飞轮侧闭环已由 ``workflow_runner._maybe_evolve`` 实现）。

定位：本存储是「反馈 → 策略」的沉淀点，writeback 的落盘处；不重造 Evolve 分析逻辑。
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List


class ContentStrategyStore:
    """按关键词（topic）维护内容策略：boost 关键词 / reduce 话题 / suggested 选题。"""

    def __init__(self, path: str = ""):
        base = os.environ.get("AOS_EVOLVE_DIR",
                              os.path.join("data", "workspaces", "fabric", "evolve"))
        os.makedirs(base, exist_ok=True)
        self._path = path or os.path.join(base, "content_strategy.json")
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {"keywords": {}, "topics": {}}
        self._load()

    # ── 写 ──

    def adjust_keywords(self, keyword: str,
                        add_keywords: List[str] = None,
                        reduce_topics: List[str] = None) -> Dict[str, Any]:
        """强化正面关键词、降低负面话题。"""
        kw = self._data["keywords"].setdefault(keyword, {"boost": [], "reduce": []})
        for a in (add_keywords or []):
            if a and a not in kw["boost"]:
                kw["boost"].append(a)
        for r in (reduce_topics or []):
            if r and r not in kw["reduce"]:
                kw["reduce"].append(r)
        self._save()
        return {"ok": True, "keyword": keyword,
                "boost": kw["boost"], "reduce": kw["reduce"]}

    def suggest_topics(self, keyword: str,
                       topics: List[str] = None) -> Dict[str, Any]:
        """记录 Evolve 推荐的新选题。"""
        t = self._data["topics"].setdefault(keyword, [])
        for tp in (topics or []):
            if tp and tp not in t:
                t.append(tp)
        self._save()
        return {"ok": True, "keyword": keyword, "topics": t}

    # ── 读 ──

    def get_strategy(self, keyword: str) -> Dict[str, Any]:
        """内容生成阶段调用：返回该关键词的偏好策略。"""
        return {
            "boost": self._data["keywords"].get(keyword, {}).get("boost", []),
            "reduce": self._data["keywords"].get(keyword, {}).get("reduce", []),
            "topics": self._data["topics"].get(keyword, []),
        }

    # ── 内部 ──

    def _load(self) -> None:
        try:
            if os.path.exists(self._path):
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self._data.setdefault("keywords", {})
                self._data.setdefault("topics", {})
        except Exception:
            pass

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


_SINGLETON: Any = None
_LOCK = threading.Lock()


def get_content_strategy() -> ContentStrategyStore:
    global _SINGLETON
    if _SINGLETON is not None:
        return _SINGLETON
    with _LOCK:
        if _SINGLETON is None:
            _SINGLETON = ContentStrategyStore()
    return _SINGLETON
