"""DeerFlow 2.0 实时技能目录 (thin-seam provider)。

AOS 侧的"实时技能目录"单一来源：直接复用 DeerFlow 网关已暴露的
``GET /api/skills`` 实时端点（DeerFlow 自身负责递归扫描
``skills/public`` 与 ``users/{uid}/skills/custom`` 并做渐进式注入），
**不在 AOS 进程内重写技能扫描逻辑**（遵守铁律：禁自研重造核心能力）。

设计要点：
- 轻量：仅做缓存 + 纯字符串匹配，不向 AOS 进程引入 DeerFlow 重依赖。
- 热加载：``refresh()`` 重新拉取网关；往 ``skills/custom`` 丢 Markdown 技能后即生效，
  无需再跑静态注册脚本。
- 失败优雅：网关不可达 / 返回 ``{"error": ...}`` 时返回空列表，调用方回落 L1-L5。
- 实时：默认 30s TTL 缓存，聊天命中时用缓存，避免每次都打网关。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 30.0  # 秒；避免每次聊天都打网关

# 技能中文/英文别名 -> 路由命中（最强信号）。覆盖 DeerFlow skills/public 的 22 个技能。
# 让用户用中文自然语言也能精准路由到对应 skill（如"做个PPT"->ppt-generation）。
SKILL_ALIASES: Dict[str, List[str]] = {
    "ppt-generation": ["ppt", "演示", "幻灯片", "汇报", "slides"],
    "deep-research": ["研究", "调研", "研报", "深度研究"],
    "frontend-design": ["前端", "网页", "界面", "页面", "ui"],
    "academic-paper-review": ["论文", "审稿", "文献", "综述"],
    "code-documentation": ["代码", "注释", "源码文档"],
    "consulting-analysis": ["咨询", "诊断"],
    "data-analysis": ["数据分析", "数据"],
    "chart-visualization": ["图表", "可视化", "绘图"],
    "image-generation": ["图片", "图像", "插画"],
    "music-generation": ["音乐", "歌曲", "作曲"],
    "podcast-generation": ["播客", "音频节目"],
    "newsletter-generation": ["新闻简报", "简报", "周刊"],
    "video-generation": ["视频", "短片"],
    "systematic-literature-review": ["文献综述", "系统综述"],
    "github-deep-research": ["github", "仓库"],
    "find-skills": ["找技能", "发现技能"],
    "skill-creator": ["创建技能", "写技能"],
    "web-design-guidelines": ["网页设计", "设计规范"],
    "surprise-me": ["惊喜", "随便来"],
    "bootstrap": ["初始化", "引导", "灵魂", "soul", "bootstrap"],
    "vercel-deploy-claimable": ["部署", "上线"],
    "claude-to-deerflow": ["迁移", "转换"],
}


@dataclass
class SkillEntry:
    name: str
    description: str = ""
    category: str = "public"
    enabled: bool = True
    editable: bool = False


class DeerFlowSkillProvider:
    """AOS 侧对 DeerFlow 实时技能目录的只读视图。

    ``fetch_skills`` 应是 ``callable() -> dict``（通常绑定到
    ``DeerFlowGatewayClient.list_skills``）。用 lambda 传入以延迟解析，
    避免捕获到初始化早期的惰性/inert 客户端。
    """

    def __init__(self, fetch_skills: Callable[[], dict], cache_ttl: float = CACHE_TTL):
        self._fetch = fetch_skills
        self._cache_ttl = cache_ttl
        self._cache: List[SkillEntry] = []
        self._ts = 0.0

    # ------------------------------------------------------------------
    #  缓存拉取
    # ------------------------------------------------------------------
    def _pull(self) -> List[SkillEntry]:
        try:
            raw = self._fetch() or {}
        except Exception as e:  # 网关不可达等
            logger.warning("DeerFlow 技能目录拉取失败, 回落: %s", e)
            return []
        if isinstance(raw, dict) and raw.get("error"):
            logger.warning("DeerFlow 技能目录返回错误: %s", raw.get("error"))
            return []
        skills = raw.get("skills") or raw.get("data") or []
        out: List[SkillEntry] = []
        for s in skills:
            if not isinstance(s, dict):
                continue
            out.append(SkillEntry(
                name=s.get("name", "") or "",
                description=s.get("description", "") or "",
                category=s.get("category", "public") or "public",
                enabled=bool(s.get("enabled", True)),
                editable=bool(s.get("editable", False)),
            ))
        return out

    def list(self) -> List[SkillEntry]:
        now = time.time()
        if now - self._ts > self._cache_ttl or not self._cache:
            self._cache = self._pull()
            self._ts = now
        return self._cache

    def refresh(self) -> List[SkillEntry]:
        """强制重拉（热加载自定义技能后调用）。"""
        self._cache = self._pull()
        self._ts = time.time()
        return self._cache

    def as_dict(self) -> Dict[str, object]:
        return {
            "count": len(self._cache),
            "skills": [
                {"name": s.name, "category": s.category, "enabled": s.enabled}
                for s in self._cache
            ],
        }

    # ------------------------------------------------------------------
    #  纯字符串匹配（不调 LLM，便宜、确定、可离线）
    # ------------------------------------------------------------------
    def match(self, message: str, threshold: float = 0.35) -> Optional[str]:
        """返回最匹配技能名；不达标返回 None。

        启发式：技能名 token 命中权重高 + 描述触发词命中 + 技能名原文出现加权。
        纯闲聊（无任何技能名/领域词命中）得分 0 -> 不路由 -> 回落 L1。
        """
        msg = (message or "").lower()
        if not msg.strip():
            return None
        best_name: Optional[str] = None
        best_score = 0.0
        for sk in self.list():
            if not sk.enabled or not sk.name:
                continue
            score = self._score(sk, msg)
            if score > best_score:
                best_score, best_name = score, sk.name
        if best_name and best_score >= threshold:
            return best_name
        return None

    @staticmethod
    def _score(sk: SkillEntry, msg: str) -> float:
        # 1) 中文/英文别名（最强信号，权重最高）
        aliases = SKILL_ALIASES.get(sk.name, [])
        alias_hits = sum(1 for a in aliases if a in msg)
        score = min(alias_hits * 0.4, 0.8)
        if score >= 0.8:  # 2 个别名命中即视为强匹配
            return 1.0

        # 2) 技能名 token 命中（英文）
        name = sk.name.lower().replace("-", " ").replace("_", " ")
        name_tokens = [t for t in name.split() if len(t) > 2]
        name_hits = sum(1 for t in name_tokens if t in msg)
        if name_tokens:
            score += (name_hits / len(name_tokens)) * 0.4

        # 3) 描述领域触发词：消息与描述同时含该英文词才算命中
        desc = sk.description.lower()
        domain_keywords = (
            "ppt", "presentation", "research", "paper", "podcast", "video",
            "image", "music", "newsletter", "frontend", "web design",
            "data analysis", "code documentation", "consulting",
            "literature", "chart", "visualization",
        )
        desc_hits = sum(1 for kw in domain_keywords if kw in desc and kw in msg)
        score += min(desc_hits, 2) * 0.1

        # 4) 技能名原文（连字符形式）直接出现，强信号
        if sk.name.lower() in msg:
            score += 0.3

        return min(score, 1.0)
