"""技能注册表（Skill Registry）——读 skills/manifest.json，桥接 FabricHub 能力。

WAIC 2026 揭示 Skill 生态化是 Agent OS 主线程（小红书 RED Skill 3700+）。AOS 已有
src/skills/ 31 个技能，但此前散布在 brain.py 的 _init_skills() 惰性注册里，
FabricHub 完全不可见。本模块为二者搭桥：

- 读 skills/manifest.json（单一真相源），不依赖 skills/__init__.py 的急加载
- 按能力(capability)反查技能：discover("web.search") → [{skill meta}]
- 为 FabricHub 提供 capability→skill 映射，让技能可被调度
- 轻量纯 stdlib（json），零导入开销（不碰任何重型适配器/引擎）

设计：
- SkillRegistry: 单例，读 manifest → 建 capability→skills 倒排索引
- discover(capability): O(1) 查出所有声明该能力的技能
- list_all(): 返回所有技能摘要
- get_skill(id): 按 id 取单个技能详情
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 仓库根取 src/skills/manifest.json
_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "skills" / "manifest.json"


class SkillRegistry:
    """技能注册表——从 manifest.json 建索引，供 FabricHub 和外部工具查询。"""

    def __init__(self, manifest_path: Optional[str] = None) -> None:
        self._manifest_path = manifest_path or str(_MANIFEST_PATH)
        self._skills: Dict[str, dict] = {}       # id → skill meta
        self._by_capability: Dict[str, List[dict]] = {}  # capability → skills
        self._loaded = False
        self.reload()

    def reload(self) -> None:
        """（重）加载 manifest 并重建倒排索引。缺失/损坏/为空零影响。"""
        path = Path(self._manifest_path)
        if not path.exists():
            logger.debug("技能清单不存在（%s），注册表为空", self._manifest_path)
            self._skills = {}
            self._by_capability = {}
            self._loaded = True
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            skills = data.get("skills", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("技能清单读取失败（%s）: %s", self._manifest_path, e)
            self._skills = {}
            self._by_capability = {}
            self._loaded = True
            return
        self._skills = {}
        self._by_capability = {}
        for s in skills:
            sid = s.get("id", "")
            if not sid:
                continue
            s.setdefault("status", "active")
            self._skills[sid] = s
            for cap in s.get("capabilities", []):
                self._by_capability.setdefault(cap, []).append(s)
        self._loaded = True
        logger.info("技能注册表加载：%d 个技能，%d 个能力",
                    len(self._skills), len(self._by_capability))

    def discover(self, capability: str) -> List[dict]:
        """按能力取值返回声明该能力的所有技能（按 name 排序）。"""
        if not self._loaded:
            self.reload()
        return sorted(
            self._by_capability.get(capability, []),
            key=lambda s: s.get("name", ""),
        )

    def list_all(self) -> List[dict]:
        if not self._loaded:
            self.reload()
        return sorted(self._skills.values(), key=lambda s: s.get("id", ""))

    def get_skill(self, skill_id: str) -> Optional[dict]:
        if not self._loaded:
            self.reload()
        return self._skills.get(skill_id)

    def summary(self) -> Dict[str, Any]:
        if not self._loaded:
            self.reload()
        return {
            "manifest": self._manifest_path,
            "loaded": self._loaded,
            "total_skills": len(self._skills),
            "total_capabilities": len(self._by_capability),
            "categories": list({s.get("category", "") for s in self._skills.values()}),
        }


# 模块级单例（惰性初始化，与 mcp/protocol._get_hub 同构）
_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        # 检测构建环境：如无 ENV("_SKILL_MANIFEST_PATH")，用默认 path
        mp = os.environ.get("AOS_SKILL_MANIFEST_PATH", "")
        _registry = SkillRegistry(manifest_path=mp or None)
    return _registry
