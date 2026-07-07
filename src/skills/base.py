"""
AOS Skill Base — 符合 agentskills.io 标准的技能基类。

每项技能包含:
- YAML frontmatter 元数据 (name, description, version, capabilities)
- execute() 方法 — 实际执行逻辑
- to_skill_md() — 导出为 Hermes 兼容的 SKILL.md 格式
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class SkillMeta:
    """技能元数据, 对应 SKILL.md 的 YAML frontmatter."""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "AOS"
    license: str = "MIT"
    platforms: List[str] = field(default_factory=lambda: ["python"])
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    category: str = "general"


class Skill:
    """AOS 技能基类.

    所有技能继承此类, 实现 execute() 方法.
    支持导出为 Hermes SKILL.md 格式供外部 Agent 发现.
    """

    NAME = "base_skill"
    DESCRIPTION = "基础技能"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "general"
    TAGS = []
    CAPABILITIES = []
    PLATFORMS = ["python"]

    def __init__(self, meta: Optional[SkillMeta] = None):
        if meta is None:
            meta = SkillMeta(
                name=self.NAME,
                description=self.DESCRIPTION,
                version=self.VERSION,
                author=self.AUTHOR,
                license=self.LICENSE,
                category=self.CATEGORY,
                tags=self.TAGS,
                capabilities=self.CAPABILITIES,
                platforms=self.PLATFORMS,
            )
        self.meta = meta
        self._log = logging.getLogger(f"skill.{meta.name}")

    @property
    def name(self) -> str:
        return self.meta.name

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能. 子类必须覆盖."""
        raise NotImplementedError(f"Skill '{self.name}' must implement execute()")

    async def execute_async(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """异步执行入口, 默认调用同步 execute()."""
        return self.execute(context)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.meta.name,
            "description": self.meta.description,
            "version": self.meta.version,
            "author": self.meta.author,
            "tags": self.meta.tags,
            "capabilities": self.meta.capabilities,
            "category": self.meta.category,
        }

    @staticmethod
    def _escape_yaml(text: str) -> str:
        return text.replace('"', '\\"')

    def to_skill_md(self) -> str:
        """导出为 Hermes 兼容的 SKILL.md 格式."""
        tags_str = ", ".join(self.meta.tags)
        caps_str = ", ".join(self.meta.capabilities)
        return (
            f"---\n"
            f"name: {self.meta.name}\n"
            f'description: "{self._escape_yaml(self.meta.description)}"\n'
            f"version: {self.meta.version}\n"
            f"author: {self.meta.author}\n"
            f"license: {self.meta.license}\n"
            f"tags: [{tags_str}]\n"
            f"platforms: [{', '.join(self.meta.platforms)}]\n"
            f"capabilities: [{caps_str}]\n"
            f"---\n\n"
            f"# {self.meta.name}\n\n"
            f"## Overview\n{self.meta.description}\n\n"
            f"## Category\n{self.meta.category}\n"
        )


class SkillRegistry:
    """AOS 技能注册中心 — 单例模式.

    负责技能的注册/发现/调用/搜索.
    与 SubAgentRegistry 协作, 将技能绑定到子智能体.
    """

    _instance: Optional["SkillRegistry"] = None

    def __new__(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills: Dict[str, Skill] = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("SkillRegistry 初始化完成")

    # ---- CRUD ----

    def register(self, skill: Skill) -> None:
        if skill.name in self._skills:
            logger.warning("技能 %s 已存在, 将被覆盖", skill.name)
        self._skills[skill.name] = skill
        logger.info("技能已注册: %s (%s)", skill.name, skill.meta.category)

    def unregister(self, name: str) -> bool:
        if name in self._skills:
            del self._skills[name]
            logger.info("技能已注销: %s", name)
            return True
        return False

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def has(self, name: str) -> bool:
        return name in self._skills

    def list_all(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._skills.values()]

    def list_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._skills.values() if s.meta.category == category]

    def list_by_tag(self, tag: str) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._skills.values() if tag in s.meta.tags]

    def search(self, query: str) -> List[Dict[str, Any]]:
        q = query.lower()
        results = []
        for skill in self._skills.values():
            d = skill.to_dict()
            haystack = f"{d['name']} {d['description']} {' '.join(d['tags'])} {' '.join(d['capabilities'])}"
            if q in haystack.lower():
                results.append(d)
        return results

    # ---- Execute ----

    def execute(self, name: str, context: Dict[str, Any]) -> Dict[str, Any]:
        skill = self._skills.get(name)
        if not skill:
            return {"success": False, "error": f"技能 '{name}' 未注册"}
        try:
            result = skill.execute(context)
            return {"success": True, "skill": name, "data": result}
        except Exception as exc:
            logger.error("技能 %s 执行失败: %s", name, exc, exc_info=True)
            return {"success": False, "skill": name, "error": str(exc)}

    # ---- Export ----

    def export_all_skill_md(self, directory: Path) -> int:
        """将所有技能导出为 SKILL.md 文件到指定目录."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        count = 0
        for skill in self._skills.values():
            filepath = directory / f"{skill.name}.md"
            filepath.write_text(skill.to_skill_md(), encoding="utf-8")
            count += 1
        logger.info("已导出 %d 个 SKILL.md 到 %s", count, directory)
        return count

    def get_stats(self) -> Dict[str, Any]:
        categories = {}
        for s in self._skills.values():
            cat = s.meta.category
            categories[cat] = categories.get(cat, 0) + 1
        return {
            "total": len(self._skills),
            "categories": categories,
            "skill_names": list(self._skills.keys()),
        }