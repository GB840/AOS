import json
import time
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class HermesAgent:
    """AOS 内置的 Hermes 代理实现。
    
    当外部 Hermes-Agent 不可用时，使用此回退实现。
    提供与真实 Hermes-Agent 兼容的 API 接口。
    """

    def __init__(self):
        self.real_hermes = False
        self._memory = []
        self._sessions = {}
        self._last_id = 0

    def chat(self, message: str, **kwargs) -> Dict[str, Any]:
        """模拟聊天回复"""
        logger.info(f"Hermes chat: {message[:50]}...")
        return {
            "response": f"Hermes 代理回复: {message}",
            "timestamp": time.time(),
            "model": "aos-hermes-fallback",
        }

    def add_knowledge(self, title: str, content: str, source: str = "", tags: List[str] = None) -> Dict[str, Any]:
        """添加知识"""
        self._memory.append({
            "id": f"mem_{len(self._memory)}",
            "title": title,
            "content": content,
            "source": source,
            "tags": tags or [],
            "added_at": time.time(),
        })
        return {"success": True, "id": self._memory[-1]["id"]}

    def search_memory(self, query: str, search_type: str = "hybrid") -> Dict[str, Any]:
        """搜索记忆"""
        results = []
        for item in self._memory:
            if query.lower() in item["title"].lower() or query.lower() in item["content"].lower():
                results.append(item)
        return {"results": results[:5], "total": len(results)}

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出会话"""
        return list(self._sessions.values())

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        return self._sessions.get(session_id)

    def close(self) -> None:
        """关闭代理"""
        logger.info("Hermes 代理已关闭")

    def __getattr__(self, name):
        """处理未实现的方法"""
        def _noop(*args, **kwargs):
            logger.warning(f"HermesAgent: 未实现方法 {name}, 参数: {args[:2]}")
            return {} if name.startswith("get") or name.startswith("search") else None
        return _noop
