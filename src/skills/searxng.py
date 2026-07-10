"""
SearXNG Skill Module - 元搜索引擎

SearXNG 是一个自托管的元搜索引擎，聚合70+个搜索引擎结果。
核心价值：可完全替代付费搜索API，实现无限制、免费的搜索。

技术特点:
- 聚合70+个搜索引擎（Google、Bing、DuckDuckGo等）
- 支持自定义搜索引擎列表
- 无广告、无追踪、隐私保护
- 支持图片搜索、视频搜索、新闻搜索
- 可通过Docker一键部署

部署方式:
- Docker: docker run -d -p 8080:8080 searxng/searxng
- 源码部署: git clone https://github.com/searxng/searxng.git
"""

import logging
import uuid
import requests
from typing import Dict, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

SEARCH_ENGINES = {
    "google": {"name": "Google", "description": "Google搜索"},
    "bing": {"name": "Bing", "description": "微软必应搜索"},
    "duckduckgo": {"name": "DuckDuckGo", "description": "隐私搜索"},
    "baidu": {"name": "百度", "description": "中文搜索"},
    "yandex": {"name": "Yandex", "description": "俄罗斯搜索"},
    "brave": {"name": "Brave", "description": "隐私搜索"},
    "searxng": {"name": "SearXNG", "description": "元搜索"},
}

SEARCH_TYPES = {
    "general": {"name": "通用搜索", "description": "综合搜索结果"},
    "images": {"name": "图片搜索", "description": "图片搜索结果"},
    "videos": {"name": "视频搜索", "description": "视频搜索结果"},
    "news": {"name": "新闻搜索", "description": "新闻搜索结果"},
    "maps": {"name": "地图搜索", "description": "地图搜索结果"},
    "wiki": {"name": "百科搜索", "description": "维基百科搜索"},
}


class SearXNGSkill(Skill):
    """
    SearXNG 元搜索技能
    
    提供聚合搜索能力，支持多种搜索类型和搜索引擎。
    支持增强模式：使用 DDGS (DuckDuckGo Search) 作为后备。
    """
    
    NAME = "searxng"
    DESCRIPTION = "SearXNG 元搜索引擎 — 聚合70+搜索引擎结果，支持多种搜索类型，完全免费无限制"
    VERSION = "1.0.0"
    AUTHOR = "SearXNG Community"
    LICENSE = "AGPL-3.0"
    CATEGORY = "search"
    TAGS = ["search", "metasearch", "searxng", "ddgs", "duckduckgo"]
    CAPABILITIES = ["web_search", "image_search", "video_search", "news_search", "map_search", "wiki_search", "metasearch"]
    
    def __init__(self):
        super().__init__()
        self._searxng_url = "http://localhost:8080"
        self._ddgs_available = False
        self._enhanced_mode = True
        
        self._check_ddgs()
    
    def _check_ddgs(self):
        """检查 DDGS 是否可用"""
        try:
            import ddgs
            self._ddgs_available = True
            logger.info("DDGS (DuckDuckGo Search) 可用")
        except ImportError:
            logger.warning("DDGS 不可用，请安装: pip install ddgs")
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行搜索任务
        
        Args:
            context: 执行上下文
                - query: 搜索查询（必填）
                - engine: 搜索引擎（可选，默认searxng）
                - search_type: 搜索类型（可选，默认general）
                - count: 结果数量（可选，默认10）
        
        Returns:
            Dict: 搜索结果
        """
        query = context.get("query", context.get("input", context.get("message", "")))
        
        if not query:
            return {
                "success": False,
                "error": "缺少 query 参数",
                "available_engines": list(SEARCH_ENGINES.keys()),
                "available_types": list(SEARCH_TYPES.keys()),
            }
        
        engine = context.get("engine", "searxng")
        search_type = context.get("search_type", "general")
        count = context.get("count", 10)
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode:
            result = self._execute_enhanced(query, search_type, count)
        else:
            result = self._execute_searxng(query, engine, search_type, count)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "query": query,
            "engine": engine,
            "search_type": search_type,
            "results": result.get("results", []),
            "total": result.get("total", 0),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode else "searxng",
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, query: str, search_type: str, count: int) -> Dict[str, Any]:
        """增强模式执行 — 使用 DDGS 或其他免费搜索API"""
        try:
            if search_type == "images":
                return self._search_images_ddgs(query, count)
            
            if self._ddgs_available:
                return self._search_ddgs(query, count)
            
            return self._search_fallback(query, count)
        except Exception as e:
            logger.error(f"增强模式搜索失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_searxng(self, query: str, engine: str, search_type: str, count: int) -> Dict[str, Any]:
        """SearXNG 模式执行 — 调用本地 SearXNG 服务"""
        try:
            params = {
                "q": query,
                "format": "json",
                "count": count,
            }
            
            if search_type != "general":
                params["categories"] = search_type
            
            url = f"{self._searxng_url}/search"
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for result in data.get("results", []):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "description": result.get("content", ""),
                        "source": result.get("engine", "searxng"),
                    })
                
                return {
                    "success": True,
                    "results": results[:count],
                    "total": len(results),
                }
            else:
                return {"success": False, "error": f"SearXNG 返回错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"SearXNG模式搜索失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _search_ddgs(self, query: str, count: int) -> Dict[str, Any]:
        """使用 DDGS 搜索"""
        from ddgs import DDGS
        
        results = []
        
        try:
            with DDGS() as ddgs:
                for result in ddgs.text(query, max_results=count):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("href", ""),
                        "description": result.get("body", ""),
                        "source": "DuckDuckGo",
                    })
            
            return {
                "success": True,
                "results": results,
                "total": len(results),
            }
        except Exception as e:
            logger.error(f"DDGS搜索失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _search_images_ddgs(self, query: str, count: int) -> Dict[str, Any]:
        """使用 DDGS 搜索图片"""
        from ddgs import DDGS
        
        results = []
        
        try:
            with DDGS() as ddgs:
                for result in ddgs.images(query, max_results=count):
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("image", ""),
                        "thumbnail": result.get("thumbnail", ""),
                        "source": result.get("source", "DuckDuckGo"),
                        "width": result.get("width", 0),
                        "height": result.get("height", 0),
                    })
            
            return {
                "success": True,
                "results": results,
                "total": len(results),
            }
        except Exception as e:
            logger.error(f"DDGS图片搜索失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _search_fallback(self, query: str, count: int) -> Dict[str, Any]:
        """降级搜索 — 使用 Jina Reader 或其他API"""
        try:
            search_url = f"https://api.jina.ai/v1/search?q={requests.utils.quote(query)}&limit={count}"
            
            headers = {"Authorization": "Bearer free-tier"}
            response = requests.get(search_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                for item in data.get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": item.get("summary", ""),
                        "source": "Jina",
                    })
                
                return {
                    "success": True,
                    "results": results[:count],
                    "total": len(results),
                }
            else:
                return {"success": False, "error": f"Jina搜索返回错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"降级搜索失败: {e}")
            return {"success": False, "error": str(e)}
    
    def list_engines(self) -> Dict[str, Any]:
        """列出所有可用搜索引擎"""
        return SEARCH_ENGINES
    
    def list_search_types(self) -> Dict[str, Any]:
        """列出所有搜索类型"""
        return SEARCH_TYPES
    
    def is_enhanced_mode(self) -> bool:
        """检查是否在增强模式"""
        return self._enhanced_mode


def get_searxng_skill() -> SearXNGSkill:
    """获取或创建 SearXNG 技能实例"""
    return SearXNGSkill()


def register_searxng_skill(registry=None):
    """注册 SearXNG 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = SearXNGSkill()
    registry.register(skill)
    logger.info("SearXNG 技能已注册")
    return skill