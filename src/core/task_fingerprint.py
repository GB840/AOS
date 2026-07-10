"""
任务指纹记忆模块 - 记忆沉淀与复用系统

核心职责:
1. 为每个任务生成唯一的"任务指纹"
2. 存储任务类型 + 角色搭配 + 编排方案
3. 查询记忆库匹配相似任务
4. 复用历史方案，避免重复跑元辩论

复用规则:
- L1/L2: 相似问答 → 直接匹配缓存
- L3: 角色搭配方案 → 有同类任务优先复用
- L4: 角色搭配 + 编排方案 → 直接复用整条工作流
- L5: 项目模板 → 下次同类项目直接套用模板

注意: 如果记忆方案超过30天未更新，即使匹配也建议重新验证
"""

import logging
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TaskTemplate:
    fingerprint: str
    task_type: str
    level: str
    role_whitelist: List[str]
    orchestration_spec: Dict[str, Any]
    model_strategy: Dict[str, str]
    cost_budget: Dict[str, Any]
    created_at: str
    last_used_at: str
    usage_count: int = 0
    success_rate: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "task_type": self.task_type,
            "level": self.level,
            "role_whitelist": self.role_whitelist,
            "orchestration_spec": self.orchestration_spec,
            "model_strategy": self.model_strategy,
            "cost_budget": self.cost_budget,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
        }


class TaskFingerprint:
    """任务指纹记忆系统"""

    def __init__(self, memory_manager=None):
        self.memory_manager = memory_manager
        self._templates: Dict[str, TaskTemplate] = {}
        self._load_templates()

    def generate_fingerprint(self, task: str) -> str:
        """生成任务指纹"""
        normalized = self._normalize_task(task)
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]

    def _normalize_task(self, task: str) -> str:
        """标准化任务描述"""
        import re
        normalized = task.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        words = sorted(normalized.split()[:20])
        return " ".join(words)

    def calculate_similarity(self, task1: str, task2: str) -> float:
        """计算两个任务的相似度"""
        fp1 = self.generate_fingerprint(task1)
        fp2 = self.generate_fingerprint(task2)
        return sum(c1 == c2 for c1, c2 in zip(fp1, fp2)) / len(fp1)

    def search_similar(self, task: str, threshold: float = 0.6) -> List[TaskTemplate]:
        """搜索相似任务"""
        candidates = []
        target_fp = self.generate_fingerprint(task)

        for template in self._templates.values():
            similarity = self._fingerprint_similarity(target_fp, template.fingerprint)
            if similarity >= threshold:
                if not self._is_outdated(template):
                    candidates.append((similarity, template))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in candidates[:5]]

    def _fingerprint_similarity(self, fp1: str, fp2: str) -> float:
        """计算指纹相似度"""
        return sum(c1 == c2 for c1, c2 in zip(fp1, fp2)) / len(fp1)

    def _is_outdated(self, template: TaskTemplate) -> bool:
        """判断模板是否过期(超过30天)"""
        try:
            created = datetime.fromisoformat(template.created_at)
            return datetime.now() - created > timedelta(days=30)
        except Exception as e:
            logger.warning("Failed to parse template created_at %r, treating as outdated: %s", template.created_at, e)
            return True

    def store_template(self, task: str, level: str, role_whitelist: List[str],
                       orchestration_spec: Dict[str, Any] = None,
                       model_strategy: Dict[str, str] = None,
                       cost_budget: Dict[str, Any] = None) -> str:
        """存储任务模板"""
        fingerprint = self.generate_fingerprint(task)
        now = datetime.now().isoformat()

        template = TaskTemplate(
            fingerprint=fingerprint,
            task_type=self._classify_task_type(task),
            level=level,
            role_whitelist=role_whitelist,
            orchestration_spec=orchestration_spec or {},
            model_strategy=model_strategy or {},
            cost_budget=cost_budget or {},
            created_at=now,
            last_used_at=now,
            usage_count=0,
            success_rate=0.0,
        )

        self._templates[fingerprint] = template
        self._save_templates()

        logger.info(f"任务模板已存储: {fingerprint} - {task[:30]}...")
        return fingerprint

    def _classify_task_type(self, task: str) -> str:
        """分类任务类型"""
        task_lower = task.lower()
        task_types = [
            ("code", ["写代码", "编程", "开发", "代码", "bug", "修复"]),
            ("analysis", ["分析", "报告", "数据", "统计", "调研"]),
            ("design", ["设计", "UI", "UX", "界面", "原型"]),
            ("writing", ["写", "文章", "文案", "报告", "文档"]),
            ("consulting", ["咨询", "建议", "方案", "策略", "规划"]),
            ("research", ["研究", "调研", "调查", "探索"]),
        ]
        for name, patterns in task_types:
            if any(p in task_lower for p in patterns):
                return name
        return "general"

    def update_template(self, fingerprint: str, **kwargs) -> bool:
        """更新任务模板"""
        if fingerprint not in self._templates:
            return False

        template = self._templates[fingerprint]
        if "success_rate" in kwargs:
            total = template.usage_count or 1
            template.success_rate = (template.success_rate * total + kwargs["success_rate"]) / (total + 1)
            template.usage_count += 1
        if "orchestration_spec" in kwargs:
            template.orchestration_spec = kwargs["orchestration_spec"]
        if "model_strategy" in kwargs:
            template.model_strategy = kwargs["model_strategy"]
        template.last_used_at = datetime.now().isoformat()

        self._save_templates()
        return True

    def get_template(self, fingerprint: str) -> Optional[TaskTemplate]:
        """获取任务模板"""
        return self._templates.get(fingerprint)

    def delete_template(self, fingerprint: str) -> bool:
        """删除任务模板"""
        if fingerprint in self._templates:
            del self._templates[fingerprint]
            self._save_templates()
            return True
        return False

    def list_templates(self, limit: int = 20) -> List[TaskTemplate]:
        """列出所有模板"""
        templates = sorted(self._templates.values(), key=lambda t: t.usage_count, reverse=True)
        return templates[:limit]

    def _load_templates(self):
        """从存储加载模板"""
        try:
            if self.memory_manager:
                data = self.memory_manager.search_knowledge_fulltext("task_template")
                for item in data:
                    try:
                        content = json.loads(item.get("content", "{}"))
                        template = TaskTemplate(**content)
                        self._templates[template.fingerprint] = template
                    except Exception as e:
                        logger.warning("Failed to parse task template entry: %s", e)
            logger.info(f"加载了 {len(self._templates)} 个任务模板")
        except Exception as e:
            logger.warning(f"加载模板失败: {e}")

    def _save_templates(self):
        """保存模板到存储"""
        try:
            if self.memory_manager:
                for template in self._templates.values():
                    content = json.dumps(template.to_dict(), ensure_ascii=False)
                    self.memory_manager.add_knowledge(
                        title=f"task_template_{template.fingerprint}",
                        content=content,
                        source="task_fingerprint",
                        tags=["task_template", template.task_type, template.level],
                    )
        except Exception as e:
            logger.warning(f"保存模板失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total = len(self._templates)
        by_level = {}
        by_type = {}

        for template in self._templates.values():
            by_level[template.level] = by_level.get(template.level, 0) + 1
            by_type[template.task_type] = by_type.get(template.task_type, 0) + 1

        return {
            "total_templates": total,
            "by_level": by_level,
            "by_type": by_type,
        }
